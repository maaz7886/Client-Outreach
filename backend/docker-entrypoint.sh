#!/bin/sh
set -e

case "$1" in
  api)
    alembic upgrade head
    exec uvicorn app.api.main:app --host 0.0.0.0 --port 8000
    ;;
  worker)
    exec celery -A app.worker.celery_app worker --loglevel=info --concurrency=2
    ;;
  beat)
    exec celery -A app.worker.celery_app beat --loglevel=info
    ;;
  *)
    exec "$@"
    ;;
esac
