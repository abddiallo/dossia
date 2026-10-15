"""Mise en forme des réponses de l'API (liens de fichiers signés inclus)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from .config import settings
from .models import Dossier, JobPosting, Profile, ProfileUpdate, StoredFile, Template, User
from .security import file_token


def file_url(file_id, user_id) -> str | None:
    if not file_id:
        return None
    return f"{settings.api_url}/api/v1/files/{file_id}?t={file_token(file_id, user_id)}"


def user_out(u: User) -> dict:
    return {"id": str(u.id), "email": u.email, "full_name": u.full_name, "plan": u.plan,
            "inbound_address": f"{u.inbound_alias}@{settings.inbound_domain}",
            "allowed_senders": u.allowed_senders or [], "defaults": u.defaults or {}}


def profile_out(p: Profile) -> dict:
    return {"id": str(p.id), "data": p.data, "version": p.version, "unverified_paths": p.unverified_paths or [],
            "updated_at": p.updated_at.isoformat() if p.updated_at else None}


def update_out(u: ProfileUpdate, db: Session) -> dict:
    f = db.get(StoredFile, u.source_file_id)
    return {"id": str(u.id), "status": u.status, "method": u.method, "diff": u.diff, "error": u.error,
            "filename": f.filename if f else None, "updated_at": u.updated_at.isoformat() if u.updated_at else None}


def template_out(t: Template, db: Session, full: bool = False) -> dict:
    f = db.get(StoredFile, t.source_file_id)
    spec = t.spec or {}
    zones = spec.get("zones", [])
    out = {
        "id": str(t.id), "esn_name": t.esn_name, "status": t.status, "kind": t.kind, "filename": f.filename if f else None,
        "recognition_score": t.recognition_score, "zones_total": len(zones),
        "zones_pending": sum(1 for z in zones if z["status"] == "pending"), "max_pages": t.max_pages,
        "original_pages": t.original_pages, "overflow_policy": t.overflow_policy, "from_library": t.from_library,
        "usage_count": t.usage_count, "error": t.error, "pages": t.original_pages,
        "thumb_url": file_url(((t.source_preview_ids or []) + (t.test_preview_ids or []) or [None])[0], t.user_id),
        "anonymize": bool((spec.get("constraints") or {}).get("anonymize")), "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }
    if full:
        out.update({
            "zones": [{k: z.get(k) for k in ("id", "key", "kind", "field", "status", "confidence", "label", "sample",
                                              "question", "choices", "suggested", "answer")} for z in zones],
            "constraints": spec.get("constraints"), "complex_notes": spec.get("complex_notes", []),
            "fidelity_report": t.fidelity_report, "cleanup_requested": t.cleanup_requested,
            "test_previews": [file_url(i, t.user_id) for i in (t.test_preview_ids or [])],
            "source_previews": [file_url(i, t.user_id) for i in (t.source_preview_ids or [])],
            "source_url": file_url(t.source_file_id, t.user_id),
        })
    return out


def dossier_out(d: Dossier, db: Session, full: bool = False) -> dict:
    t = db.get(Template, d.template_id)
    jp = db.get(JobPosting, d.job_posting_id) if d.job_posting_id else None
    out = {
        "id": str(d.id), "status": d.status, "esn_name": t.esn_name if t else None, "template_id": str(d.template_id),
        "template_status": t.status if t else None, "channel": d.channel,
        "job_posting": {"id": str(jp.id), "title": jp.title, "sectors": jp.extracted.get("sectors", [])} if jp else None,
        "pages": d.pages, "max_pages": d.max_pages, "origin_stats": d.origin_stats, "question": d.question,
        "docx_url": file_url(d.output_docx_id, d.user_id), "pdf_url": file_url(d.output_pdf_id, d.user_id),
        "preview_urls": [file_url(i, d.user_id) for i in (d.preview_ids or [])],
        "generation_ms": d.generation_ms, "anonymized": (d.view or {}).get("anonymized"),
        "adapted": bool(jp) and (d.options or {}).get("adapt", True), "filename": d.output_filename,
        "error": d.error, "created_at": d.created_at.isoformat() if d.created_at else None,
        "updated_at": d.updated_at.isoformat() if d.updated_at else None,
        "can_undo": bool(d.options_history),
        "highlight_preview_urls": [file_url(i, d.user_id) for i in (d.highlight_preview_ids or [])],
    }
    if full:
        out.update({
            "segments": d.segments or [], "fidelity_report": d.fidelity_report, "adjustments": d.adjustments or [],
            "options": {k: v for k, v in (d.options or {}).items() if k != "rephrased"},
            "messages": [{"role": m.role, "content": m.content, "changes": m.changes, "proposal": m.proposal,
                          "created_at": m.created_at.isoformat() if m.created_at else None} for m in d.messages],
            "suggestions": ["Raccourcir la synthèse", "Ajouter ma disponibilité", "Moins de réalisations par mission"],
            "missions": _dossier_missions(d, db),
            "settings": {"anonymize": bool((d.view or {}).get("anonymized")),
                         "adapt": (d.options or {}).get("adapt", True) is not False,
                         "max_pages": (d.options or {}).get("max_pages") or d.max_pages},
        })
    return out


def _dossier_missions(d: Dossier, db: Session) -> list[dict]:
    """Missions du profil pour « Missions incluses » : incluse, retirée par l'utilisateur ou retirée pour la limite de pages."""
    prof = db.get(Profile, d.profile_id) if d.profile_id else None
    if not prof:
        return []
    hidden = set((d.options or {}).get("hidden", []))
    shown = {m.get("id") for m in (d.view or {}).get("missions", [])}
    out = []
    for m in sorted(prof.data.get("missions", []), key=lambda m: m.get("debut") or "0000", reverse=True):
        debut, fin = (m.get("debut") or "")[:4], (m.get("fin") or "")[:4]
        state = "hidden" if m["id"] in hidden else ("included" if m["id"] in shown or not d.view else "dropped")
        out.append({"id": m["id"], "client": m.get("client") or "Mission", "poste": m.get("poste") or "",
                    "period": f"{debut} – {fin or 'aujourd’hui'}" if debut else "", "state": state})
    return out
