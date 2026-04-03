import logging
import os

from dotenv import load_dotenv
load_dotenv()

import click
from flask import Flask, session
from flask_login import current_user
from sqlalchemy import event

from flask_compress import Compress

from app.config import Config, ProdConfig
from app.extensions import db, login_manager, bcrypt, csrf

logger = logging.getLogger(__name__)


def create_app():
    flask_app = Flask(__name__)

    config = ProdConfig if os.environ.get('FLASK_ENV') == 'production' else Config
    flask_app.config.from_object(config)

    # Initialise extensions
    db.init_app(flask_app)
    login_manager.init_app(flask_app)
    bcrypt.init_app(flask_app)
    csrf.init_app(flask_app)
    Compress(flask_app)

    login_manager.login_view = 'auth.login'

    # SQLite PRAGMAs — must be registered after db.init_app
    with flask_app.app_context():
        @event.listens_for(db.engine, "connect")
        def set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    # User loader for Flask-Login
    @login_manager.user_loader
    def load_user(user_id):
        from app.models.user import User
        return db.session.get(User, int(user_id))

    # Import all models so SQLAlchemy registers them
    import app.models  # noqa: F401

    # Theme context processor — injects resolved theme + helpers into all templates
    @flask_app.context_processor
    def inject_theme():
        from app.cache import get_cached_theme
        from app.services.theme import score_to_colour, score_to_style, pct_to_colour, rating_cell_style, unrated_to_colour
        from app.constants import RATING_KEY_STANDARD, RATING_KEY_STEALTH
        if current_user.is_authenticated:
            theme = get_cached_theme(current_user)
        else:
            theme = {}
        return {
            'theme': theme,
            'score_to_colour': lambda v: score_to_colour(v, theme),
            'score_to_style': lambda v: score_to_style(v, theme),
            'pct_to_colour': lambda v: pct_to_colour(v, theme),
            'rating_cell_style': lambda s: rating_cell_style(s, theme),
            'unrated_to_colour': lambda v: unrated_to_colour(v, theme),
            'RATING_KEY_STANDARD': RATING_KEY_STANDARD,
            'RATING_KEY_STEALTH': RATING_KEY_STEALTH,
        }

    # Filter context processor — injects country/genre filters + dropdown options
    @flask_app.context_processor
    def inject_filters():
        from app.cache import get_cached_filters
        if current_user.is_authenticated:
            if not current_user.is_system_or_guest and current_user.settings:
                country_id = current_user.settings.country
                genre_id = current_user.settings.genre
            else:
                country_id = session.get('country')
                genre_id = session.get('genre')
            countries, genres, genders = get_cached_filters()
            return {
                'current_country': country_id,
                'current_genre': genre_id,
                'countries': countries,
                'genres': genres,
                'genders': genders,
            }
        return {'current_country': None, 'current_genre': None, 'countries': [], 'genres': [], 'genders': []}

    # Prevent bfcache so theme/session changes are always reflected on back navigation
    @flask_app.after_request
    def no_bfcache(response):
        content_type = response.content_type or ''
        if 'text/html' in content_type:
            response.headers['Cache-Control'] = 'no-store'
        return response

    # 404 error page
    @flask_app.errorhandler(404)
    def page_not_found(e):
        from flask import render_template
        return render_template('404.html'), 404

    # First-deploy: copy bundled DB to persistent volume, or seed if no DB exists
    db_path = flask_app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
    if db_path.startswith('/') and not os.path.exists(db_path):
        bundled = os.path.join(flask_app.root_path, '..', 'arima_seed.db')
        if os.path.exists(bundled):
            import shutil
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            shutil.copy2(bundled, db_path)
            logger.info('Copied bundled database to %s', db_path)
        else:
            with flask_app.app_context():
                db.create_all()
                _create_last_updated_triggers(db)
                from app.seed import seed
                seed(db)
                logger.info('Seeded new database at %s', db_path)

    # Temporary upload endpoint — remove after initial deploy
    @flask_app.route('/upload-db', methods=['GET', 'POST'])
    @csrf.exempt
    def upload_db():
        from flask import request
        upload_secret = os.environ.get('UPLOAD_SECRET')
        if not upload_secret:
            return 'UPLOAD_SECRET env var not set', 403
        if request.args.get('key') != upload_secret:
            return 'Forbidden', 403
        if request.method == 'GET':
            return '''<form method="post" enctype="multipart/form-data">
                <input type="file" name="db" accept=".db">
                <button type="submit">Upload</button>
            </form>'''
        f = request.files.get('db')
        if not f:
            return 'No file', 400
        target = flask_app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
        os.makedirs(os.path.dirname(target), exist_ok=True)
        f.save(target)
        return f'Database uploaded to {target} ({os.path.getsize(target)} bytes)'

    # Register routes
    from app.routes import register_routes
    register_routes(flask_app)

    # One-time migration: add any new theme colour columns to existing DB
    with flask_app.app_context():
        try:
            from app.models.theme import Theme
            existing = {row[1] for row in db.session.execute(db.text("PRAGMA table_info('theme')"))}
            for col in Theme.__table__.columns:
                if col.name not in existing and col.name not in ('id', 'name', 'user_id'):
                    db.session.execute(db.text(f'ALTER TABLE theme ADD COLUMN {col.name} TEXT'))
                    logger.info('Added missing theme column: %s', col.name)
            db.session.commit()
        except Exception:
            db.session.rollback()
            pass  # DB may not exist yet

    # Validate system themes on startup
    with flask_app.app_context():
        try:
            from app.models.theme import Theme
            colour_cols = [c.name for c in Theme.__table__.columns
                           if c.name not in ('id', 'name', 'user_id')]
            for theme_id, theme_name in ((0, 'Classic'), (1, 'Dark')):
                theme = db.session.get(Theme, theme_id)
                if theme:
                    for col in colour_cols:
                        if getattr(theme, col) is None:
                            logger.warning('%s theme (id=%d) has NULL value for column: %s', theme_name, theme_id, col)
        except Exception:
            pass  # DB may not exist yet (first run before seed)

    # One-time schema migration: make rating.rating nullable (note-only entries)
    with flask_app.app_context():
        try:
            row = db.session.execute(
                db.text("SELECT sql FROM sqlite_master WHERE type='table' AND name='rating'")
            ).scalar()
            if row and 'rating INTEGER NOT NULL' in row:
                logger.info('Migrating rating table: making rating column nullable')
                db.session.execute(db.text('PRAGMA foreign_keys=OFF'))
                db.session.execute(db.text(
                    'CREATE TABLE rating_new ('
                    'song_id INTEGER NOT NULL, '
                    'user_id INTEGER NOT NULL, '
                    'rating INTEGER, '
                    'note TEXT, '
                    'PRIMARY KEY (song_id, user_id), '
                    'CONSTRAINT rating_range CHECK (rating >= 0 AND rating <= 5), '
                    'FOREIGN KEY(song_id) REFERENCES song (id) ON DELETE CASCADE, '
                    'FOREIGN KEY(user_id) REFERENCES user (id) ON DELETE CASCADE)'
                ))
                db.session.execute(db.text(
                    'INSERT INTO rating_new SELECT * FROM rating'
                ))
                db.session.execute(db.text('DROP TABLE rating'))
                db.session.execute(db.text('ALTER TABLE rating_new RENAME TO rating'))
                db.session.execute(db.text('PRAGMA foreign_keys=ON'))
                db.session.commit()
                logger.info('Rating table migration complete')
        except Exception:
            db.session.rollback()
            pass  # DB may not exist yet

    # One-time migration: add missing indexes for existing databases
    with flask_app.app_context():
        try:
            for idx_sql in [
                'CREATE INDEX IF NOT EXISTS ix_artist_artist_relationship ON artist_artist (relationship)',
                'CREATE INDEX IF NOT EXISTS ix_rating_user_id ON rating (user_id)',
            ]:
                db.session.execute(db.text(idx_sql))
            db.session.commit()
        except Exception:
            db.session.rollback()
            pass  # DB may not exist yet

    def _create_last_updated_triggers(database):
        """Create SQLite triggers that auto-set last_updated on row updates."""
        for table in ('artist', 'song', 'album', 'user'):
            database.session.execute(database.text(f"""
                CREATE TRIGGER IF NOT EXISTS trg_{table}_last_updated
                AFTER UPDATE ON {table}
                BEGIN
                    UPDATE {table} SET last_updated = strftime('%Y-%m-%dT%H:%M:%S', 'now')
                    WHERE id = NEW.id;
                END;
            """))
        database.session.commit()

    # Flask CLI: seed command
    @flask_app.cli.command('seed')
    def seed_command():
        """Create all tables and insert seed data."""
        db.create_all()
        _create_last_updated_triggers(db)
        from app.seed import seed
        seed(db)
        click.echo('Database seeded.')

    @flask_app.cli.command('import-jpop')
    def import_jpop_command():
        """Import JPOP data from 'lettuce jpop.xlsx'."""
        from scripts.import_jpop_data import import_jpop
        import_jpop()
        click.echo('JPOP import complete.')

    @flask_app.cli.command('import-kpop-notes')
    def import_kpop_notes_command():
        """Import cell comment notes from 'lettuce kpop.xlsx'."""
        from scripts.import_kpop_notes import import_kpop_notes
        import_kpop_notes()
        click.echo('Kpop notes import complete.')

    @flask_app.cli.command('fix-missing-songs')
    def fix_missing_songs_command():
        """Import Q=False songs that were missed inside album contexts."""
        from scripts.fix_missing_songs import fix_missing_songs
        fix_missing_songs()
        click.echo('Fix complete.')

    @flask_app.cli.command('fetch-album-dates')
    def fetch_album_dates_command():
        """Fetch exact release dates for albums from MusicBrainz."""
        from scripts.fetch_album_dates import fetch_album_dates
        fetch_album_dates()
        click.echo('Album date fetch complete.')

    @flask_app.cli.command('import-rock')
    def import_rock_command():
        """Import data from 'lettuce billy joel.xlsx'."""
        from scripts.import_rock_data import import_rock
        import_rock()
        click.echo('Rock import complete.')

    return flask_app
