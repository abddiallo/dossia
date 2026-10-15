"""Tâche de nuit (cron / tâche planifiée) : python -m app.maintenance — purge RGPD des fichiers sources expirés."""
from __future__ import annotations

from .db import session_scope
from .storage import purge_expired

if __name__ == "__main__":
    with session_scope() as db:
        print(f"{purge_expired(db)} fichier(s) expiré(s) supprimé(s)")
