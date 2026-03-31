import logging
import os

import click
from flask import Flask, session
from flask_login import current_user
from sqlalchemy import event

from app.config import Config, ProdConfig
from app.extensions import db, login_manager, bcrypt

logger = logging.getLogger(__name__)


def create_app():
    flask_app = Flask(__name__)

    config = ProdConfig if os.environ.get('FLASK_ENV') == 'production' else Config
    flask_app.config.from_object(config)

    # Initialise extensions
    db.init_app(flask_app)
    login_manager.init_app(flask_app)
    bcrypt.init_app(flask_app)

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
        from app.services.theme import get_resolved_theme, score_to_colour, pct_to_colour, rating_cell_style
        from app.constants import RATING_KEY_STANDARD, RATING_KEY_STEALTH
        if current_user.is_authenticated:
            theme = get_resolved_theme(current_user)
        else:
            theme = {}
        return {
            'theme': theme,
            'score_to_colour': lambda v: score_to_colour(v, theme),
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

    # Register routes
    from app.routes import register_routes
    register_routes(flask_app)

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

    @flask_app.cli.command('merge-users')
    def merge_users_command():
        """Merge Stealth (imported) into Stealth_Robot (admin)."""
        from app.models.user import User
        from app.models.music import Rating

        stealth_robot = User.query.filter_by(username='Stealth_Robot').first()
        stealth = User.query.filter_by(username='Stealth').first()

        if not stealth:
            click.echo('No "Stealth" user found — nothing to merge.')
            return
        if not stealth_robot:
            click.echo('No "Stealth_Robot" user found.')
            return

        with db.session.no_autoflush:
            # Transfer ratings
            rating_count = Rating.query.filter_by(user_id=stealth.id).update(
                {Rating.user_id: stealth_robot.id}
            )

            # Save sort_order before clearing
            new_sort = stealth.sort_order

            # Clear Stealth's sort_order to avoid UNIQUE conflict
            stealth.sort_order = None
            db.session.flush()

            # Transfer sort_order
            if new_sort is not None:
                stealth_robot.sort_order = new_sort

            # Delete Stealth (cascades UserSettings)
            db.session.delete(stealth)

        db.session.commit()

        click.echo(f'Merged: {rating_count} ratings transferred, Stealth user deleted.')

    return flask_app
