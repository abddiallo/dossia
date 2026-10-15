"""Worker des tâches de fond : python -m app.worker"""
from __future__ import annotations

import logging

from redis import Redis
from rq import Queue, Worker

from .config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

if __name__ == "__main__":
    if not settings.redis_url:
        raise SystemExit("REDIS_URL est requis pour lancer le worker.")
    conn = Redis.from_url(settings.redis_url)
    Worker([Queue("dossia", connection=conn)], connection=conn).work(with_scheduler=False)
