import logging
import os

import click
from flask import Flask, session
from flask_login import current_user
from sqlalchemy import event

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
        from app.services.theme import get_resolved_theme, score_to_colour, score_to_style, pct_to_colour, rating_cell_style
        from app.constants import RATING_KEY_STANDARD, RATING_KEY_STEALTH
        if current_user.is_authenticated:
            theme = get_resolved_theme(current_user)
        else:
            theme = {}
        return {
            'theme': theme,
            'score_to_colour': lambda v: score_to_colour(v, theme),
            'score_to_style': lambda v: score_to_style(v, theme),
            'pct_to_colour': lambda v: pct_to_colour(v, theme),
            'rating_cell_style': lambda s: rating_cell_style(s, theme),
            'RATING_KEY_STANDARD': RATING_KEY_STANDARD,
            'RATING_KEY_STEALTH': RATING_KEY_STEALTH,
        }

    # Filter context processor — injects country/genre filters + dropdown options
    @flask_app.context_processor
    def inject_filters():
        from app.models.lookups import Country, Genre
        if current_user.is_authenticated:
            if not current_user.is_system_or_guest and current_user.settings:
                country_id = current_user.settings.country
                genre_id = current_user.settings.genre
            else:
                country_id = session.get('country')
                genre_id = session.get('genre')
            return {
                'current_country': country_id,
                'current_genre': genre_id,
                'countries': Country.query.order_by(Country.id).all(),
                'genres': Genre.query.order_by(Genre.id).all(),
            }
        return {'current_country': None, 'current_genre': None, 'countries': [], 'genres': []}

    # Prevent bfcache so theme/session changes are always reflected on back navigation
    @flask_app.after_request
    def no_bfcache(response):
        response.headers['Cache-Control'] = 'no-store'
        return response

    # Register routes
    from app.routes import register_routes
    register_routes(flask_app)

    # Add artist_button_text column to theme table if it doesn't exist
    with flask_app.app_context():
        try:
            with db.engine.connect() as conn:
                cols = [row[1] for row in conn.execute(db.text("PRAGMA table_info(theme)")).fetchall()]
                if 'artist_button_text' not in cols:
                    conn.execute(db.text("ALTER TABLE theme ADD COLUMN artist_button_text VARCHAR(7)"))
                    conn.commit()
        except Exception:
            pass  # DB may not exist yet

    # Add navbar_active column to theme table if it doesn't exist
    with flask_app.app_context():
        try:
            with db.engine.connect() as conn:
                cols = [row[1] for row in conn.execute(db.text("PRAGMA table_info(theme)")).fetchall()]
                if 'navbar_active' not in cols:
                    conn.execute(db.text("ALTER TABLE theme ADD COLUMN navbar_active VARCHAR(7)"))
                    conn.commit()
        except Exception:
            pass  # DB may not exist yet

    # Validate Classic theme on startup
    with flask_app.app_context():
        try:
            from app.models.theme import Theme
            classic = db.session.get(Theme, 0)
            if classic:
                colour_cols = [c.name for c in Theme.__table__.columns
                               if c.name not in ('id', 'name', 'user_id')]
                for col in colour_cols:
                    if getattr(classic, col) is None:
                        logger.warning('Classic theme (id=0) has NULL value for column: %s', col)
        except Exception:
            pass  # DB may not exist yet (first run before seed)

    # Flask CLI: seed command
    @flask_app.cli.command('seed')
    def seed_command():
        """Create all tables and insert seed data."""
        db.create_all()
        from app.seed import seed
        seed(db)
        click.echo('Database seeded.')

    @flask_app.cli.command('import-data')
    @click.argument('json_file')
    def import_data_command(json_file):
        """Import data from exported JSON file."""
        from scripts.import_data import import_data
        import_data(json_file)

    @flask_app.cli.command('migrate-slugs')
    def migrate_slugs_command():
        """Add slug column to artist table and backfill slugs for existing rows."""
        from app.services.artist import generate_unique_slug
        from app.models.music import Artist

        # Add the column if it doesn't exist (SQLite-safe)
        with db.engine.connect() as conn:
            cols = [row[1] for row in conn.execute(db.text("PRAGMA table_info(artist)")).fetchall()]
            if 'slug' not in cols:
                conn.execute(db.text("ALTER TABLE artist ADD COLUMN slug VARCHAR(100)"))
                conn.execute(db.text("CREATE UNIQUE INDEX IF NOT EXISTS ix_artist_slug ON artist (slug)"))
                conn.commit()
                click.echo('Added slug column to artist table.')
            else:
                click.echo('slug column already exists.')

        # Backfill missing slugs
        artists = Artist.query.filter(Artist.slug.is_(None)).all()
        used_slugs = {a.slug for a in Artist.query.filter(Artist.slug.isnot(None)).all()}
        updated = 0
        for artist in artists:
            slug = generate_unique_slug(artist.name, used_slugs)
            artist.slug = slug
            used_slugs.add(slug)
            updated += 1
        db.session.commit()
        click.echo(f'Backfilled {updated} artist slugs.')

    return flask_app
