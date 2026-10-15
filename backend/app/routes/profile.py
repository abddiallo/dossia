from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..engine.cv_extract import apply_diff
from ..models import ProfileUpdate, User
from ..security import current_user
from ..serializers import profile_out, update_out
from ..services import pipeline

router = APIRouter(prefix="/profile", tags=["profil"])


class ProfileIn(BaseModel):
    data: dict
    verified_paths: list[str] = []


class ApplyIn(BaseModel):
    accepted: list[str] | None = None


@router.get("")
def get_profile(user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = pipeline.get_profile(db, user)
    db.commit()
    return profile_out(p)


@router.put("")
def put_profile(body: ProfileIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = pipeline.get_profile(db, user)
    remaining = [x for x in (p.unverified_paths or []) if x not in body.verified_paths]
    pipeline.save_profile_data(db, p, body.data, remaining)
    db.commit()
    pipeline._trigger_waiting(db, user.id)
    return profile_out(p)


@router.get("/updates")
def list_updates(user: User = Depends(current_user), db: Session = Depends(get_db)):
    ups = db.scalars(select(ProfileUpdate).where(ProfileUpdate.user_id == user.id,
                                                 ProfileUpdate.status.in_(["extracting", "ready", "failed"]))
                     .order_by(ProfileUpdate.updated_at.desc())).all()
    return [update_out(u, db) for u in ups]


def _update(db: Session, user: User, update_id: uuid.UUID) -> ProfileUpdate:
    u = db.get(ProfileUpdate, update_id)
    if not u or u.user_id != user.id:
        raise HTTPException(404, "Mise à jour introuvable")
    return u


@router.post("/updates/{update_id}/apply")
def apply_update(update_id: uuid.UUID, body: ApplyIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    u = _update(db, user, update_id)
    if u.status != "ready" or not u.diff:
        raise HTTPException(409, "Rien à appliquer")
    p = pipeline.get_profile(db, user)
    pipeline.save_profile_data(db, p, apply_diff(p.data, u.diff, body.accepted))
    u.status = "applied"
    db.commit()
    pipeline._trigger_waiting(db, user.id)
    return profile_out(p)


@router.post("/updates/{update_id}/dismiss")
def dismiss_update(update_id: uuid.UUID, user: User = Depends(current_user), db: Session = Depends(get_db)):
    u = _update(db, user, update_id)
    u.status = "dismissed"
    db.commit()
    return {"ok": True}


class SkillIn(BaseModel):
    label: str
    mission_id: str | None = None


class SayIn(BaseModel):
    message: str


@router.post("/skills")
def add_skill(body: SkillIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """« Je l'ai » : l'utilisateur confirme une compétence demandée par l'offre (ajoutée à la mission choisie s'il y en a une)."""
    from ..engine.skills import canonical
    from ..engine.text import norm
    label, cat = canonical(body.label.strip())
    if not label:
        raise HTTPException(422, "Compétence vide")
    p = pipeline.get_profile(db, user)
    data = dict(p.data)
    comps = list(data.get("competences", []))
    if not any(norm(c["label"]) == norm(label) for c in comps):
        comps.append({"label": label, "categorie": cat, "niveau": None})
    data["competences"] = comps
    if body.mission_id:
        missions = [dict(m) for m in data.get("missions", [])]
        for m in missions:
            if m.get("id") == body.mission_id and label not in m.get("environnement", []):
                m["environnement"] = [*m.get("environnement", []), label]
        data["missions"] = missions
    pipeline.save_profile_data(db, p, data)
    db.commit()
    return profile_out(p)


@router.post("/assistant")
def say(body: SayIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """« Dites-le simplement » : une phrase → modification du profil."""
    from ..engine.profile_assistant import interpret
    p = pipeline.get_profile(db, user)
    r = interpret(body.message[:500], p.data)
    if r["changes"]:
        pipeline.save_profile_data(db, p, r["profile"])
        db.commit()
        pipeline._trigger_waiting(db, user.id)
    return {"reply": r["reply"], "changes": r["changes"], "profile": profile_out(p)}
