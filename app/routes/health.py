from flask import Blueprint, send_from_directory, current_app

health_bp = Blueprint('health', __name__)


@health_bp.route('/health')
def health():
    return 'ok', 200


@health_bp.route('/reset-sw')
def reset_sw():
    return '''<!DOCTYPE html><html><head><title>Reset</title></head><body>
<script>
if('serviceWorker' in navigator){
    navigator.serviceWorker.getRegistrations().then(function(regs){
        regs.forEach(function(r){r.unregister();});
        document.body.textContent='Service worker unregistered. Redirecting...';
        setTimeout(function(){location.href='/';},1000);
    });
} else { location.href='/'; }
</script>
<p>Resetting...</p></body></html>''', 200, {'Content-Type': 'text/html'}


@health_bp.route('/sw.js')
def service_worker():
    resp = send_from_directory(current_app.static_folder, 'sw.js')
    resp.headers['Service-Worker-Allowed'] = '/'
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp
