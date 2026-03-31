import logging
import os

import click
from flask import Flask
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

    login_manager.login_view = 'login'

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

    return flask_app
