import os

from flask import Blueprint, request

health_bp = Blueprint('health', __name__)


@health_bp.route('/health')
def health():
    return 'ok', 200


@health_bp.route('/upload-db', methods=['PUT'])
def upload_db():
    from flask import current_app
    current_app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB
    secret = os.environ.get('UPLOAD_SECRET')
    if not secret or request.headers.get('X-Upload-Secret') != secret:
        return 'forbidden', 403
    db_path = '/data/arima.db'
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with open(db_path, 'wb') as f:
        f.write(request.get_data())
    return 'ok', 200
