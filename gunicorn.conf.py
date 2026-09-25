# Fenix production WSGI config — Flask's dev server is for development only.
# Run: gunicorn -c gunicorn.conf.py server:app
import os

bind = "0.0.0.0:" + str(os.environ.get("PORT", "8010"))
workers = int(os.environ.get("GUNICORN_WORKERS", "2"))
threads = int(os.environ.get("GUNICORN_THREADS", "8"))
timeout = 300
graceful_timeout = 30
loglevel = "info"
accesslog = "-"
