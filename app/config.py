import os


class Config:
    SECRET_KEY = os.environ['SECRET_KEY']
    PEPPER = os.environ['PEPPER']
    SQLALCHEMY_DATABASE_URI = 'sqlite:///arima.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Host that serves the simuls surface (Option A: same app, host-based routing).
    # Override locally (e.g. 'simuls.localhost:8000') to test the split.
    SIMUL_HOST = os.environ.get('SIMUL_HOST', 'simuls.stealth-robot.com')
    PERMANENT_SESSION_LIFETIME = 2592000  # 30 days in seconds
    WTF_CSRF_TIME_LIMIT = None            # CSRF token valid for life of session
    SESSION_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_SAMESITE = 'Lax'
    COMPRESS_MIMETYPES = [
        'text/html', 'text/css', 'text/javascript',
        'application/javascript', 'application/json',
    ]
    COMPRESS_MIN_SIZE = 500


class ProdConfig(Config):
    SQLALCHEMY_DATABASE_URI = 'sqlite:////data/arima.db'
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    # Share the login session across arima.* and simuls.* subdomains. One-time
    # effect on deploy: existing host-only cookies are replaced by domain cookies
    # (everyone is logged out once). The cookie is sent to every *.stealth-robot.com.
    SESSION_COOKIE_DOMAIN = '.stealth-robot.com'
    REMEMBER_COOKIE_DOMAIN = '.stealth-robot.com'
