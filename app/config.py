import os


class Config:
    SECRET_KEY = os.environ['SECRET_KEY']
    PEPPER = os.environ['PEPPER']
    SQLALCHEMY_DATABASE_URI = 'sqlite:///arima.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
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
