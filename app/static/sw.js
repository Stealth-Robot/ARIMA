// Force new SW to activate immediately, replacing any buggy cached version
self.addEventListener('install', function() { self.skipWaiting(); });
self.addEventListener('activate', function(event) { event.waitUntil(clients.claim()); });

self.addEventListener('fetch', function(event) {
    if (event.request.mode !== 'navigate') return;
    if (event.request.method === 'GET') {
        event.respondWith(
            fetch(event.request).then(function(response) {
                // Only show deploy page for 502/503 (Railway proxy errors during container swap).
                // Let everything else through: 200, 302, 404, 500, etc.
                if (response.status === 502 || response.status === 503) return deployingPage();
                return response;
            }).catch(function() {
                // Network error = container completely unreachable
                return deployingPage();
            })
        );
    } else if (event.request.method === 'POST') {
        // Keep the form body so the deploy page can resubmit it once the app is back
        var copy = event.request.clone();
        event.respondWith(
            copy.arrayBuffer().then(function(body) {
                var replay = {
                    url: event.request.url,
                    type: event.request.headers.get('Content-Type') || '',
                    body: toBase64(body)
                };
                return fetch(event.request).then(function(response) {
                    if (response.status === 502 || response.status === 503) return deployingPage(replay);
                    return response;
                }).catch(function() {
                    return deployingPage(replay);
                });
            })
        );
    }
});

function toBase64(buffer) {
    var bytes = new Uint8Array(buffer), s = '';
    for (var i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    return btoa(s);
}

function deployingPage(replay) {
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
        '<p>' + (replay ? 'The app is restarting. Your changes will be saved automatically once it is back.'
                        : 'The app is restarting. This page will refresh automatically.') + '</p>' +
        '<div class="spinner"></div>' +
        '</div>' +
        '<script>window.onbeforeunload=null;' +
        'if("serviceWorker" in navigator)navigator.serviceWorker.register("/sw.js");' +
        'var replay=' + JSON.stringify(replay || null).replace(/</g, '\\u003c') + ',busy=false;' +
        'function resend(){' +
        'var raw=atob(replay.body),bytes=new Uint8Array(raw.length);' +
        'for(var i=0;i<raw.length;i++)bytes[i]=raw.charCodeAt(i);' +
        'var headers=replay.type?{"Content-Type":replay.type}:{};' +
        'return fetch(replay.url,{method:"POST",body:bytes,headers:headers,credentials:"same-origin"}).then(function(r){' +
        'if(r.status===502||r.status===503)return;' +
        'clearInterval(timer);' +
        'if(r.redirected)return location.replace(r.url);' +
        'return r.text().then(function(html){document.open();document.write(html);document.close();});' +
        '});}' +
        'var timer=setInterval(function(){if(busy)return;busy=true;fetch("/health").then(function(r){' +
        'if(!r.ok)return;' +
        'if(replay)return resend();' +
        'location.replace(location.href);}).catch(function(){}).then(function(){busy=false;});},3000);</script>' +
        '</body></html>',
        {status: 503, headers: {'Content-Type': 'text/html'}}
    );
}
