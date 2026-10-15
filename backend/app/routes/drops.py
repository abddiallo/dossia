"""Dépôt unique : un seul point d'entrée pour CV, modèles et fiches de poste.  [D1]"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..security import current_user
from ..services import pipeline

router = APIRouter(tags=["dépôt"])
MAX_FILE = 15 * 1024 * 1024


@router.post("/drops")
async def drop(files: list[UploadFile] = File(default=[]), pasted_text: str | None = Form(None),
               auto_dossier: bool = Form(True), expected: str | None = Form(None),
               user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not files and not (pasted_text or "").strip():
        raise HTTPException(422, "Déposez au moins un fichier ou collez une fiche de poste.")
    data = []
    for f in files[:10]:
        content = await f.read()
        if len(content) > MAX_FILE:
            raise HTTPException(413, f"« {f.filename} » dépasse 15 Mo.")
        data.append((f.filename or "fichier", content))
    return pipeline.handle_drop(db, user, data, pasted_text=pasted_text, auto_dossier=auto_dossier,
                               expected=expected if expected in ("template", "cv") else None)
