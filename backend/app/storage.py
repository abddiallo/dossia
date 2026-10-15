"""
Stockage des fichiers. V1 : disque local (volume Docker) sous DATA_DIR/<utilisateur>/.
Pour la production : remplacer les 3 fonctions par un stockage objet chiffré hébergé en UE
(OVH / Scaleway, compatible S3).
"""
from __future__ import annotations

import hashlib
import mimetypes
import shutil
import uuid
from datetime import timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from .config import settings
from .db import utcnow
from .models import StoredFile

RETAINED_KINDS = {"cv", "template", "job_posting", "email"}  # sources purgées après la durée de rétention


def _abs(key: str) -> Path:
    p = (settings.data_dir / key).resolve()
    if settings.data_dir not in p.parents:
        raise ValueError("chemin invalide")
    return p


def path_of(f: StoredFile) -> Path:
    return _abs(f.storage_key)


def save_bytes(db: Session, user_id: uuid.UUID, kind: str, filename: str, data: bytes, mime: str | None = None) -> StoredFile:
    fid = uuid.uuid4()
    ext = Path(filename).suffix.lower()[:10]
    key = f"{user_id}/{fid}{ext}"
    dest = _abs(key)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    f = StoredFile(
        id=fid, user_id=user_id, kind=kind, filename=Path(filename).name[:255] or f"fichier{ext}",
        mime=mime or mimetypes.guess_type(filename)[0] or "application/octet-stream",
        storage_key=key, sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data),
        expires_at=(utcnow() + timedelta(days=settings.source_retention_days)) if kind in RETAINED_KINDS else None,
    )
    db.add(f)
    db.flush()
    return f


def save_path(db: Session, user_id: uuid.UUID, kind: str, src: Path, filename: str | None = None) -> StoredFile:
    return save_bytes(db, user_id, kind, filename or src.name, Path(src).read_bytes())


def workdir(*parts: str) -> Path:
    p = settings.data_dir / "_work" / Path(*parts)
    p.mkdir(parents=True, exist_ok=True)
    return p


def delete_user_files(user_id: uuid.UUID) -> None:
    shutil.rmtree(settings.data_dir / str(user_id), ignore_errors=True)


def purge_expired(db: Session) -> int:
    """À lancer chaque nuit (tâche planifiée) : supprime les fichiers sources expirés."""
    n = 0
    for f in db.query(StoredFile).filter(StoredFile.expires_at.isnot(None), StoredFile.expires_at < utcnow()).all():
        try:
            path_of(f).unlink(missing_ok=True)
        except ValueError:
            pass
        db.delete(f)
        n += 1
    return n
