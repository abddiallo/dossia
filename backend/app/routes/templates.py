"""Modèles d'ESN : bibliothèque, questions, test, bibliothèque partagée.  [D2] [D4]"""
from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Template, User
from ..queue import enqueue
from ..security import current_user
from ..serializers import template_out
from ..services import pipeline

router = APIRouter(prefix="/templates", tags=["modèles"])


class TemplatePatch(BaseModel):
    esn_name: str | None = None
    max_pages: int | None = None
    overflow_policy: Literal["keep_recent", "shorten", "allow_extra_page"] | None = None


class AnswersIn(BaseModel):
    answers: dict[str, str]


def _get(db: Session, user: User, template_id: uuid.UUID) -> Template:
    t = db.get(Template, template_id)
    if not t or t.user_id != user.id:
        raise HTTPException(404, "Modèle introuvable")
    return t


@router.get("")
def list_templates(user: User = Depends(current_user), db: Session = Depends(get_db)):
    pipeline.reconcile(db, user)
    ts = db.scalars(select(Template).where(Template.user_id == user.id).order_by(Template.updated_at.desc())).all()
    return [template_out(t, db) for t in ts]


@router.get("/{template_id}")
def get_template(template_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return template_out(_get(db, user, template_id), db, full=True)


@router.patch("/{template_id}")
def patch_template(template_id: uuid.UUID, body: TemplatePatch, user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    t = _get(db, user, template_id)
    retest = False
    if body.esn_name is not None:
        t.esn_name = body.esn_name.strip()[:160]
    if body.max_pages is not None:
        t.max_pages, retest = max(1, body.max_pages), True
    if body.overflow_policy:
        t.overflow_policy, retest = body.overflow_policy, True
    db.commit()
    if retest and t.status == "ready":
        enqueue(pipeline.job_template_test, str(t.id))
    return template_out(t, db, full=True)


@router.post("/{template_id}/answers")
def answer(template_id: uuid.UUID, body: AnswersIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = _get(db, user, template_id)
    pipeline.answer_template(db, t, body.answers)
    return template_out(t, db, full=True)


@router.post("/{template_id}/validate")
def validate(template_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """« Enregistrer le modèle » : alimente la bibliothèque partagée (sans données personnelles)."""
    t = _get(db, user, template_id)
    if t.status != "ready":
        raise HTTPException(409, "Répondez d'abord aux questions sur le modèle.")
    pipeline.contribute_to_library(db, t)
    db.commit()
    return template_out(t, db, full=True)


@router.post("/{template_id}/cleanup-request")
def cleanup(template_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = _get(db, user, template_id)
    if user.plan != "team":
        raise HTTPException(402, "La remise au propre des modèles est incluse dans l'offre Équipe.")
    t.cleanup_requested = True
    db.commit()
    return {"ok": True}


@router.delete("/{template_id}", status_code=204)
def delete(template_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(_get(db, user, template_id))
    db.commit()
