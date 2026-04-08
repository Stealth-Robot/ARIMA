self.addEventListener('fetch', function(event) {
    if (event.request.mode !== 'navigate') return;
    event.respondWith(
        fetch(event.request).then(function(response) {
            if (response.ok || response.status === 304) return response;
            return deployingPage();
        }).catch(function() {
            return deployingPage();
        })
    );
});

function deployingPage() {
    return new Response(
        '<!DOCTYPE html><html><head><meta charset="UTF-8">' +
        '<meta name="viewport" content="width=device-width,initial-scale=1">' +
        '<title>A.R.I.M.A.</title>' +
        '<style>body{background:#111;color:#ccc;font-family:Arial,sans-serif;' +
        'display:flex;justify-content:center;align-items:center;height:100vh;margin:0;' +
        'text-align:center;}' +
        '.box{max-width:400px;}h1{font-size:20px;margin-bottom:8px;}' +
        'p{font-size:14px;opacity:0.7;}' +
        '.spinner{width:24px;height:24px;border:3px solid #333;border-top-color:#ccc;' +
        'border-radius:50%;animation:spin 0.8s linear infinite;margin:16px auto 0;}' +
        '@keyframes spin{to{transform:rotate(360deg);}}</style>' +
        '</head><body><div class="box">' +
        '<h1>Deploying update...</h1>' +
        '<p>The app is restarting. This page will refresh automatically.</p>' +
        '<div class="spinner"></div>' +
        '</div>' +
        '<script>setInterval(function(){fetch("/health").then(function(r){' +
        'if(r.ok)location.reload();}).catch(function(){});},3000);</script>' +
        '</body></html>',
        {status: 503, headers: {'Content-Type': 'text/html'}}
    );
}
