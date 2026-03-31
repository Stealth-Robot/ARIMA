import os

import click
from flask import Flask
from sqlalchemy import event

from app.config import Config, ProdConfig
from app.extensions import db, login_manager, bcrypt


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

    # Flask CLI: seed command
    @flask_app.cli.command('seed')
    def seed_command():
        """Create all tables and insert seed data."""
        db.create_all()
        from app.seed import seed
        seed(db)
        click.echo('Database seeded.')

    return flask_app
