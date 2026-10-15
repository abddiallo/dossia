"""Dossiers : génération, assistant, sources des reformulations, retouches.  [D1] [D3]"""
from __future__ import annotations

import copy
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Dossier, JobPosting, Profile, Template, User
from ..security import current_user
from ..serializers import dossier_out
from ..services import pipeline
from ..services.emailer import send_dossier_reply

router = APIRouter(prefix="/dossiers", tags=["dossiers"])


class DossierIn(BaseModel):
    template_id: uuid.UUID
    job_posting_id: uuid.UUID | None = None
    posting_text: str | None = None
    options: dict | None = None


class AssistantIn(BaseModel):
    message: str | None = None
    choice: str | None = None     # réponse à la question unique


class OptionsIn(BaseModel):
    anonymize: bool | None = None
    adapt: bool | None = None
    max_pages: int | None = None
    hidden_missions: list[str] | None = None   # missions retirées de CE dossier (le profil n'est pas modifié)


class SegmentPatch(BaseModel):
    key: str
    final_text: str | None = None
    decision: str | None = None   # accepted | reverted
    hidden: bool | None = None
    apply_to_profile: bool = False


def _get(db: Session, user: User, dossier_id: uuid.UUID) -> Dossier:
    d = db.get(Dossier, dossier_id)
    if not d or d.user_id != user.id:
        raise HTTPException(404, "Dossier introuvable")
    return d


@router.get("")
def list_dossiers(user: User = Depends(current_user), db: Session = Depends(get_db)):
    pipeline.reconcile(db, user)
    ds = db.scalars(select(Dossier).where(Dossier.user_id == user.id).order_by(Dossier.created_at.desc()).limit(200)).all()
    return [dossier_out(d, db) for d in ds]


@router.post("", status_code=202)
def create(body: DossierIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = db.get(Template, body.template_id)
    if not t or t.user_id != user.id:
        raise HTTPException(404, "Modèle introuvable")
    jp = db.get(JobPosting, body.job_posting_id) if body.job_posting_id else None
    if body.posting_text and body.posting_text.strip():
        jp = pipeline.create_posting(db, user, body.posting_text, "paste")
    d = pipeline.create_dossier(db, user, t, jp, body.options)
    return dossier_out(d, db)


@router.get("/{dossier_id}")
def get(dossier_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    pipeline.reconcile(db, user)
    return dossier_out(_get(db, user, dossier_id), db, full=True)


@router.post("/{dossier_id}/assistant")
def assistant(dossier_id: uuid.UUID, body: AssistantIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = _get(db, user, dossier_id)
    if d.status in ("queued", "generating", "waiting_template", "needs_profile"):
        raise HTTPException(409, "Le dossier est en cours de génération, un instant…")
    if body.choice:
        pipeline.answer_question(db, d, body.choice)
        reply = {"reply": "C'est noté.", "changes": [], "proposal": None}
    elif body.message and body.message.strip():
        reply = pipeline.apply_assistant(db, d, body.message.strip()[:1000])
    else:
        raise HTTPException(422, "Message vide")
    return {**reply, "dossier": dossier_out(d, db, full=True)}


@router.patch("/{dossier_id}/segments")
def patch_segment(dossier_id: uuid.UUID, body: SegmentPatch, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    d = _get(db, user, dossier_id)
    pipeline.patch_segment(db, d, body.key, body.final_text, body.decision, body.hidden, body.apply_to_profile)
    return dossier_out(d, db, full=True)


@router.post("/{dossier_id}/undo")
def undo(dossier_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = _get(db, user, dossier_id)
    if not pipeline.undo(db, d):
        raise HTTPException(409, "Rien à annuler")
    return dossier_out(d, db, full=True)


@router.post("/{dossier_id}/regenerate")
def regenerate(dossier_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = _get(db, user, dossier_id)
    o = dict(d.options or {})
    o.pop("rephrased", None)  # nouvelle adaptation (profil ou fiche de poste modifiés)
    pipeline.push_options(d, o)
    pipeline.regenerate(db, d)
    return dossier_out(d, db, full=True)


@router.post("/{dossier_id}/options")
def set_options(dossier_id: uuid.UUID, body: OptionsIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Réglages de l'écran « Le dossier » : pages, anonymisation, adaptation, missions incluses."""
    d = _get(db, user, dossier_id)
    if d.status in ("queued", "generating"):
        raise HTTPException(409, "Le dossier est en cours de génération, un instant…")
    o = copy.deepcopy(d.options or {})
    if body.anonymize is not None:
        o["anonymize"] = body.anonymize
    if body.adapt is not None:
        o["adapt"] = body.adapt
    if body.max_pages is not None:
        o["max_pages"] = max(1, min(10, body.max_pages))
    if body.hidden_missions is not None:
        prof = db.get(Profile, d.profile_id)
        mission_ids = {m["id"] for m in prof.data.get("missions", [])}
        keep = [h for h in o.get("hidden", []) if h not in mission_ids]
        o["hidden"] = keep + [h for h in body.hidden_missions if h in mission_ids]
    pipeline.push_options(d, o)
    pipeline.regenerate(db, d)
    return dossier_out(d, db, full=True)


@router.post("/{dossier_id}/email")
def email_me(dossier_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    d = _get(db, user, dossier_id)
    if d.status not in ("ready", "needs_answer"):
        raise HTTPException(409, "Le dossier n'est pas encore prêt")
    send_dossier_reply(db, d)
    return {"sent": True}


@router.delete("/{dossier_id}", status_code=204)
def delete(dossier_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(_get(db, user, dossier_id))
    db.commit()
