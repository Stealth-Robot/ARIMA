import logging
import os

from dotenv import load_dotenv
load_dotenv()

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

    @login_manager.unauthorized_handler
    def unauthorized():
        """Return login page with 200 instead of 302 redirect.

        This is critical for service worker compatibility — old SWs only pass
        through 200 responses. A 302 triggers the deploy page, permanently
        locking out unauthenticated users.
        """
        from flask import request, url_for, render_template
        return render_template('auth/login.html', next=request.url), 200

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

    # Let known bot crawlers through auth so OG meta tags render per-page
    _BOT_KEYWORDS = ['bot', 'crawl', 'spider', 'slack', 'discord', 'facebook',
                     'twitter', 'whatsapp', 'linkedin', 'googlebot']

    @login_manager.request_loader
    def load_bot_user(req):
        ua = (req.headers.get('User-Agent') or '').lower()
        if any(kw in ua for kw in _BOT_KEYWORDS):
            from app.models.user import User
            return db.session.get(User, 1)  # Guest user
        return None

    # Import all models so SQLAlchemy registers them
    import app.models  # noqa: F401

    # Update last_seen on every request, stash previous value for update notification
    @flask_app.before_request
    def update_last_seen():
        from datetime import datetime, timezone
        from flask import g
        if current_user.is_authenticated and not current_user.is_system_or_guest:
            g.previous_last_seen = current_user.last_seen
            current_user.last_seen = datetime.now(timezone.utc).isoformat()
            db.session.commit()

    # Update notification — inject latest update ID for client-side dismissal tracking
    @flask_app.context_processor
    def inject_update_notification():
        if current_user.is_authenticated and not current_user.is_system_or_guest:
            from app.models.update import Update
            latest = Update.query.order_by(Update.id.desc()).first()
            if latest:
                return {'latest_update_id': latest.id}
        return {'latest_update_id': 0}

    # Theme context processor — injects resolved theme + helpers into all templates
    @flask_app.context_processor
    def inject_theme():
        from app.cache import get_cached_theme
        from app.services.theme import score_to_colour, score_to_style, pct_to_colour, rating_cell_style, unrated_to_colour
        from app.models.user import DEFAULT_RATING_LABELS
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
            'DEFAULT_RATING_LABELS': DEFAULT_RATING_LABELS,
        }

    # Filter context processor — injects country/genre filters + dropdown options
    @flask_app.context_processor
    def inject_filters():
        from app.cache import get_cached_filters
        if current_user.is_authenticated:
            if not current_user.is_system_or_guest and current_user.settings:
                country_id = current_user.settings.country
                genre_id = current_user.settings.genre
                song_button_size = current_user.settings.song_button_size
            else:
                country_id = session.get('country')
                genre_id = session.get('genre')
                song_button_size = session.get('song_button_size', 13)
            countries, genres, genders, album_types = get_cached_filters()
            return {
                'current_country': country_id,
                'current_genre': genre_id,
                'countries': countries,
                'genres': genres,
                'genders': genders,
                'album_types': album_types,
                'song_button_size': song_button_size,
            }
        return {'current_country': None, 'current_genre': None, 'countries': [], 'genres': [], 'genders': [], 'album_types': [], 'song_button_size': 13}

    # TEMPORARY: Convert 302 redirects to client-side redirects (200 + JS) so old
    # service workers that only pass through 200 responses don't get stuck in a loop.
    # Remove this once all users have the new SW (after ~1 week from 2026-04-08).
    @flask_app.after_request
    def sw_safe_redirect(response):
        from flask import request
        if response.status_code in (301, 302, 303, 307, 308) and request.method == 'GET':
            location = response.headers.get('Location', '/')
            response = flask_app.make_response(
                '<html><head><script>location.replace(' + repr(location) + ');</script>'
                '<meta http-equiv="refresh" content="0;url=' + location + '">'
                '</head><body></body></html>', 200)
            response.headers['Content-Type'] = 'text/html'
        content_type = response.content_type or ''
        if 'text/html' in content_type:
            response.headers['Cache-Control'] = 'no-store'
        if request.path == '/sw.js':
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return response

    # CSRF token expired — redirect with flash message instead of silent redirect
    from flask_wtf.csrf import CSRFError

    @flask_app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        from flask import request, redirect, flash, url_for, session
        logger.warning('CSRF error on %s %s: %s', request.method, request.path, e.description)
        try:
            flash('Your session expired. Please try again.', 'error')
            if request.form:
                session['_csrf_form_data'] = {k: v for k, v in request.form.items() if k != 'csrf_token'}
        except Exception:
            pass
        try:
            fallback = request.referrer or url_for('home.home')
        except Exception:
            fallback = '/'
        return redirect(fallback)

    # Log all unhandled exceptions
    @flask_app.errorhandler(Exception)
    def handle_exception(e):
        import traceback
        from flask import request
        from werkzeug.exceptions import HTTPException
        if isinstance(e, HTTPException) and e.code < 500:
            raise e
        logger.error('Unhandled %s on %s %s:\n%s',
                     type(e).__name__, request.method, request.path,
                     traceback.format_exc())
        if isinstance(e, HTTPException):
            return e.get_body(), e.code
        return 'Internal Server Error', 500

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
                from app.migrations import create_last_updated_triggers
                db.create_all()
                create_last_updated_triggers(db)
                from app.seed import seed
                seed(db)
                logger.info('Seeded new database at %s', db_path)

    # Register routes
    from app.routes import register_routes
    register_routes(flask_app)

    # Register CLI commands
    from app.cli import register_cli
    register_cli(flask_app)

    # Startup migrations — skip if SKIP_MIGRATIONS is set (run separately before gunicorn)
    if os.environ.get('SKIP_MIGRATIONS'):
        return flask_app

    with flask_app.app_context():
        from app.migrations import run_startup_migrations
        run_startup_migrations()

    # Start backup scheduler (production only, after migrations)
    from app.services.backup import start_backup_scheduler
    start_backup_scheduler(flask_app)

    return flask_app
