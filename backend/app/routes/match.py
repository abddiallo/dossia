"""Étape « L'offre » : correspondance entre l'offre et le profil, avec les positions à surligner.  [D3]"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..engine.match import match
from ..models import JobPosting, User
from ..security import current_user
from ..services import pipeline

router = APIRouter(tags=["offre"])


class MatchIn(BaseModel):
    text: str | None = None
    job_posting_id: uuid.UUID | None = None


@router.post("/match")
def match_posting(body: MatchIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.job_posting_id:
        jp = db.get(JobPosting, body.job_posting_id)
        if not jp or jp.user_id != user.id:
            raise HTTPException(404, "Offre introuvable")
    elif body.text and body.text.strip():
        jp = pipeline.create_posting(db, user, body.text.strip(), "paste")
        db.commit()
    else:
        raise HTTPException(422, "Collez le texte de l'offre.")
    prof = pipeline.get_profile(db, user)
    db.commit()
    return {"job_posting": {"id": str(jp.id), "title": jp.title, "text": jp.raw_text},
            **match(prof.data, jp.raw_text)}
