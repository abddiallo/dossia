"""Jetons signés (HMAC) : lien magique, session, liens de fichiers. Aucune dépendance externe."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import User

LOGIN_TTL = 20 * 60
SESSION_TTL = 30 * 24 * 3600
FILE_TTL = 12 * 3600


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def sign(payload: dict, ttl: int) -> str:
    body = _b64(json.dumps({**payload, "exp": int(time.time()) + ttl}, separators=(",", ":")).encode())
    sig = _b64(hmac.new(settings.secret_key.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify(token: str, typ: str) -> dict:
    try:
        body, sig = token.split(".", 1)
        expected = _b64(hmac.new(settings.secret_key.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            raise ValueError("signature")
        data = json.loads(_unb64(body))
        if data.get("typ") != typ or data["exp"] < time.time():
            raise ValueError("expiré")
        return data
    except Exception as e:  # noqa: BLE001
        raise HTTPException(401, "Lien ou session invalide, reconnectez-vous.") from e


def login_token(email: str) -> str:
    return sign({"typ": "login", "email": email.lower()}, LOGIN_TTL)


def session_token(user_id: uuid.UUID) -> str:
    return sign({"typ": "session", "uid": str(user_id)}, SESSION_TTL)


def file_token(file_id: uuid.UUID, user_id: uuid.UUID) -> str:
    return sign({"typ": "file", "fid": str(file_id), "uid": str(user_id)}, FILE_TTL)


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    auth = request.headers.get("authorization", "")
    token = auth[7:] if auth.lower().startswith("bearer ") else request.query_params.get("token", "")
    if not token:
        raise HTTPException(401, "Non connecté")
    data = verify(token, "session")
    user = db.get(User, uuid.UUID(data["uid"]))
    if not user or user.deleted_at:
        raise HTTPException(401, "Compte introuvable")
    return user
