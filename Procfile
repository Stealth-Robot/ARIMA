web: MALLOC_ARENA_MAX=2 gunicorn "app:create_app()" --bind 0.0.0.0:$PORT --workers 1 --threads 11 --graceful-timeout 30 --capture-output --error-logfile -
