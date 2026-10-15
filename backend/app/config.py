"""Configuration par variables d'environnement (voir .env.example)."""
from __future__ import annotations

import os
from pathlib import Path


def _bool(v: str | None, default: bool = False) -> bool:
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "oui")


class Settings:
    database_url = os.environ.get("DATABASE_URL", "postgresql+psycopg://dossia:dossia@localhost:5432/dossia")
    redis_url = os.environ.get("REDIS_URL", "")            # vide → tâches exécutées dans un thread (dev)
    data_dir = Path(os.environ.get("DATA_DIR", "./data")).resolve()
    secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    dev_mode = _bool(os.environ.get("DEV_MODE"), True)
    frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:5173").rstrip("/")
    api_url = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")
    cors_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]

    # e-mail sortant
    smtp_host = os.environ.get("SMTP_HOST", "")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_password = os.environ.get("SMTP_PASSWORD", "")
    mail_from = os.environ.get("MAIL_FROM", "Dossia <depot@dossia.fr>")

    # e-mail entrant [D1]
    inbound_domain = os.environ.get("INBOUND_DOMAIN", "depot.dossia.fr")
    inbound_webhook_secret = os.environ.get("INBOUND_WEBHOOK_SECRET", "change-me")
    inbound_require_auth = _bool(os.environ.get("INBOUND_REQUIRE_SPF_DKIM"), True)

    # rétention RGPD
    source_retention_days = int(os.environ.get("SOURCE_RETENTION_DAYS", "180"))

    # offre gratuite
    free_dossiers_per_month = int(os.environ.get("FREE_DOSSIERS_PER_MONTH", "3"))


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
