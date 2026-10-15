"""
File de tâches. Avec REDIS_URL : RQ (worker séparé, `python -m app.worker`).
Sans Redis (développement) : la tâche s'exécute dans un thread, le parcours reste identique.
"""
from __future__ import annotations

import logging
import threading

from .config import settings

log = logging.getLogger("dossia.queue")
_queue = None


def _rq():
    global _queue
    if _queue is None:
        from redis import Redis
        from rq import Queue
        _queue = Queue("dossia", connection=Redis.from_url(settings.redis_url), default_timeout=600)
    return _queue


def enqueue(func, *args) -> None:
    if settings.redis_url:
        _rq().enqueue(func, *args)
        return

    def run():
        try:
            func(*args)
        except Exception:  # noqa: BLE001
            log.exception("Tâche %s échouée", getattr(func, "__name__", func))
    threading.Thread(target=run, daemon=True).start()
