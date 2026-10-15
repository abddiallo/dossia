"""Point d'entrée de l'API : uvicorn app.main:app"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import init_db
from .engine import llm
from .routes import auth, dossiers, drops, match, misc, profile, templates

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(title="Dossia API", version="1.0.0",
              description="Génération de dossiers de compétences fidèles aux modèles des ESN.")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

for r in (auth.router, drops.router, match.router, profile.router, templates.router, dossiers.router, misc.router):
    app.include_router(r, prefix="/api/v1")


VERSION = "2.0.0"


@app.on_event("startup")
def _startup() -> None:
    init_db()
    logging.getLogger("dossia").info("Dossia %s · IA %s", VERSION, "activée" if llm.available() else "désactivée (mode heuristique)")


@app.get("/health")
def health():
    return {"ok": True, "version": VERSION, "ia": llm.available(), "queue": "redis" if settings.redis_url else "thread"}
