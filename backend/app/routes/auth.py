"""Connexion sans mot de passe : lien magique envoyé par e-mail."""
from __future__ import annotations

import re
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..engine.text import norm
from ..models import User
from ..security import login_token, session_token, verify
from ..serializers import user_out
from ..services.emailer import send_login_link

router = APIRouter(prefix="/auth", tags=["auth"])
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class LinkIn(BaseModel):
    email: str


class VerifyIn(BaseModel):
    token: str


def _alias(db: Session, email: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "", norm(email.split("@")[0]))[:20] or "moi"
    alias = base
    while db.scalars(select(User).where(User.inbound_alias == alias)).first():
        alias = f"{base}{secrets.randbelow(9000) + 1000}"
    return alias


@router.post("/request-link")
def request_link(body: LinkIn, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(422, "Adresse e-mail invalide")
    link = f"{settings.frontend_url}/connexion?token={login_token(email)}"
    send_login_link(email, link)
    return {"sent": True, "dev_link": link if settings.dev_mode else None}


@router.post("/verify")
def verify_link(body: VerifyIn, db: Session = Depends(get_db)):
    data = verify(body.token, "login")
    email = data["email"]
    user = db.scalars(select(User).where(User.email == email)).first()
    if user is None:
        user = User(email=email, inbound_alias=_alias(db, email), allowed_senders=[], defaults={"adapt": True})
        db.add(user)
        db.commit()
    return {"session_token": session_token(user.id), "user": user_out(user)}
