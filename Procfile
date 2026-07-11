web: MALLOC_ARENA_MAX=2 gunicorn "app:create_app()" --bind 0.0.0.0:$PORT --workers 1 --threads 11 --graceful-timeout 30 --max-requests 800 --max-requests-jitter 200 --capture-output --error-logfile -
