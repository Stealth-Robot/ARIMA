from flask import Blueprint, send_from_directory, current_app

health_bp = Blueprint('health', __name__)


@health_bp.route('/health')
def health():
    return 'ok', 200


@health_bp.route('/sw.js')
def service_worker():
    resp = send_from_directory(current_app.static_folder, 'sw.js')
    resp.headers['Service-Worker-Allowed'] = '/'
    resp.headers['Cache-Control'] = 'no-cache'
    return resp
