# Fenix AI — production image.
#
# Fenix is a Python/Flask service that also serves its own front end, so the
# image is a single process bound to $PORT. gunicorn.conf.py already binds
# 0.0.0.0:$PORT and allows a 300s request, which is what the streaming chat
# endpoint and the long model calls need.
FROM python:3.11-slim

# curl is used by the container healthcheck below; nothing else needs it.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first so a code change does not reinstall the world.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Only what the running service actually reads: the app, the api package, the
# video brain it imports, and the front end it serves. The training notebooks,
# the HF Spaces and the Modal apps are not part of a running server.
COPY server.py gunicorn.conf.py ./
COPY api/ ./api/
COPY fenix-video/api/ ./fenix-video/api/
COPY web/ ./web/

# The account, conversation, memory and quota files live here. On a host with a
# real volume this is the mount point; on a free tier it is container-local and
# is replaced whenever the instance is recycled — the app reports which it is
# rather than letting a user believe their data is still there.
ENV FENIX_DATA_DIR=/data \
    PORT=8010 \
    PYTHONUNBUFFERED=1
RUN mkdir -p /data && useradd --system --uid 10001 fenix && chown fenix:fenix /data
VOLUME ["/data"]

USER fenix
EXPOSE 8010

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/healthz" || exit 1

CMD ["gunicorn", "-c", "gunicorn.conf.py", "server:app"]
