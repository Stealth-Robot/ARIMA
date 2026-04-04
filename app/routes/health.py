import base64
import os

from flask import Blueprint, request

from app.extensions import csrf

health_bp = Blueprint('health', __name__)


@health_bp.route('/health')
def health():
    return 'ok', 200


@csrf.exempt
@health_bp.route('/upload-db', methods=['PUT'])
def upload_db():
    secret = os.environ.get('UPLOAD_SECRET')
    if not secret or request.headers.get('X-Upload-Secret') != secret:
        return 'forbidden', 403
    db_path = '/data/arima.db'
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    with open(db_path, 'wb') as f:
        f.write(base64.b64decode(request.get_data()))
    return 'ok', 200
