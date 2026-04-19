web: gunicorn fyp_backend.wsgi:application --bind 0.0.0.0:$PORT --preload --timeout 600 --graceful-timeout 30 --workers 1 --worker-class sync
