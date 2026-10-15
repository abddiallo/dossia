"""Fichiers signés, webhook e-mail entrant, compte (RGPD), flux d'événements temps réel."""
from __future__ import annotations

import io
import json
import time
import uuid
import zipfile
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import storage
from ..config import settings
from ..db import SessionLocal, get_db, utcnow
from ..models import Dossier, Profile, ProfileUpdate, StoredFile, Template, User
from ..security import current_user, verify
from ..serializers import dossier_out, profile_out, template_out, update_out, user_out
from ..services import inbound

router = APIRouter()


# ───────────── Fichiers (liens signés, utilisables dans <img> et en téléchargement) ─────────────

@router.get("/files/{file_id}", tags=["fichiers"])
def get_file(file_id: uuid.UUID, t: str, download: int = 0, db: Session = Depends(get_db)):
    data = verify(t, "file")
    if data["fid"] != str(file_id):
        raise HTTPException(403, "Lien invalide")
    f = db.get(StoredFile, file_id)
    if not f or str(f.user_id) != data["uid"]:
        raise HTTPException(404, "Fichier introuvable")
    disp = "attachment" if download or f.kind.startswith("output") else "inline"
    return FileResponse(storage.path_of(f), media_type=f.mime, filename=f.filename,
                        content_disposition_type=disp)


# ───────────── E-mail entrant [D1] ─────────────

@router.post("/webhooks/inbound-email", status_code=200, tags=["e-mail"])
async def inbound_email(request: Request, db: Session = Depends(get_db)):
    secret = request.headers.get("x-webhook-secret") or request.query_params.get("secret")
    if secret != settings.inbound_webhook_secret:
        raise HTTPException(401, "Secret invalide")
    payload = await request.json()
    return inbound.process(db, payload)


# ───────────── Compte ─────────────

class MePatch(BaseModel):
    full_name: str | None = None
    allowed_senders: list[str] | None = None
    defaults: dict | None = None


@router.get("/me", tags=["compte"])
def me(user: User = Depends(current_user)):
    return user_out(user)


@router.patch("/me", tags=["compte"])
def patch_me(body: MePatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.full_name is not None:
        user.full_name = body.full_name.strip()[:200]
    if body.allowed_senders is not None:
        user.allowed_senders = sorted({s.strip().lower() for s in body.allowed_senders if "@" in s})[:10]
    if body.defaults is not None:
        allowed = {"adapt", "anonymize", "anonymize_clients", "realisations_max"}
        user.defaults = {k: v for k, v in body.defaults.items() if k in allowed}
    db.commit()
    return user_out(user)


@router.get("/me/export", tags=["compte"])
def export(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Export RGPD : toutes les données et tous les fichiers de l'utilisateur."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("compte.json", json.dumps(user_out(user), ensure_ascii=False, indent=2))
        prof = db.scalars(select(Profile).where(Profile.user_id == user.id)).all()
        z.writestr("profil.json", json.dumps([profile_out(p) for p in prof], ensure_ascii=False, indent=2, default=str))
        ds = db.scalars(select(Dossier).where(Dossier.user_id == user.id)).all()
        z.writestr("dossiers.json", json.dumps([dossier_out(d, db, full=True) for d in ds], ensure_ascii=False, indent=2, default=str))
        for f in db.scalars(select(StoredFile).where(StoredFile.user_id == user.id, StoredFile.kind != "preview")):
            p = storage.path_of(f)
            if p.exists():
                z.write(p, f"fichiers/{f.kind}/{f.id}-{f.filename}")
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip",
                             headers={"Content-Disposition": 'attachment; filename="dossia-export.zip"'})


@router.delete("/me", status_code=204, tags=["compte"])
def delete_me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Suppression définitive. La bibliothèque partagée ne contient aucune donnée personnelle."""
    storage.delete_user_files(user.id)
    db.delete(user)
    db.commit()


# ───────────── Événements temps réel (SSE) ─────────────

@router.get("/events", tags=["temps réel"])
def events(token: str):
    data = verify(token, "session")
    uid = uuid.UUID(data["uid"])

    def stream():
        since = utcnow() - timedelta(seconds=5)
        seen: dict[str, str] = {}
        yield "retry: 3000\n\n"
        for _ in range(1200):  # ~30 min, le navigateur se reconnecte ensuite
            time.sleep(1.5)
            db = SessionLocal()
            try:
                now = utcnow()
                out = []
                for t in db.scalars(select(Template).where(Template.user_id == uid, Template.updated_at > since)):
                    out.append({"type": "template", "data": template_out(t, db)})
                for d in db.scalars(select(Dossier).where(Dossier.user_id == uid, Dossier.updated_at > since)):
                    out.append({"type": "dossier", "data": dossier_out(d, db)})
                for u in db.scalars(select(ProfileUpdate).where(ProfileUpdate.user_id == uid, ProfileUpdate.updated_at > since)):
                    out.append({"type": "profile_update", "data": update_out(u, db)})
                since = now - timedelta(seconds=5)  # recouvrement : rien n'est manqué
            finally:
                db.close()
            fresh = []
            for ev in out:  # dédoublonnage dû au recouvrement
                sig = f'{ev["data"].get("status")}|{ev["data"].get("updated_at")}'  # (les liens signés changent à chaque appel)
                if seen.get(ev["type"] + ev["data"]["id"]) != sig:
                    seen[ev["type"] + ev["data"]["id"]] = sig
                    fresh.append(ev)
            out = fresh
            for ev in out:
                yield f"event: {ev['type']}\ndata: {json.dumps(ev['data'], default=str)}\n\n"
            if not out:
                yield ": ping\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
