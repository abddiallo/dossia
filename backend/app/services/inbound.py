"""
Dépôt par e-mail.  [D1]

L'utilisateur transfère l'e-mail de l'ESN à <alias>@depot.dossia.fr. Le fournisseur d'e-mails
entrants (Postmark, Brevo, Mailgun…) appelle notre webhook en JSON. Format attendu (Postmark,
les autres fournisseurs se ramènent facilement à celui-ci) :
  From, FromFull{Email}, To / ToFull[{Email}], Subject, TextBody, MessageID, Headers[{Name, Value}],
  Attachments[{Name, Content (base64), ContentType}]

Sécurité : secret du webhook (vérifié par la route), alias → utilisateur, expéditeur autorisé,
SPF/DKIM valides, idempotence sur Message-ID.
"""
from __future__ import annotations

import base64
import logging
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Dossier, InboundEmail, User
from . import pipeline
from .emailer import send_simple_reply

log = logging.getLogger("dossia.inbound")


def _header(payload: dict, name: str) -> str:
    for h in payload.get("Headers", []) or []:
        if h.get("Name", "").lower() == name.lower():
            return h.get("Value", "")
    return ""


def _recipients(payload: dict) -> list[str]:
    out = [x.get("Email", "") for x in payload.get("ToFull", []) or []]
    out += [x.get("Email", "") for x in payload.get("CcFull", []) or []]
    if payload.get("OriginalRecipient"):
        out.append(payload["OriginalRecipient"])
    if not out and payload.get("To"):
        out = re.findall(r"[\w.+-]+@[\w.-]+", payload["To"])
    return [o.lower() for o in out if o]


def _auth_ok(payload: dict) -> bool:
    if not settings.inbound_require_auth:
        return True
    spf = _header(payload, "Received-SPF").lower()
    ar = _header(payload, "Authentication-Results").lower()
    return ("pass" in spf) or ("dkim=pass" in ar) or ("spf=pass" in ar)


def strip_quoted(body: str) -> str:
    """Garde la réponse de l'utilisateur, sans le message cité."""
    lines = []
    for line in (body or "").splitlines():
        if line.startswith(">") or re.match(r"^\s*(Le .+ a écrit|On .+ wrote|-----\s*Original|De\s*:|From\s*:)", line):
            break
        lines.append(line)
    return "\n".join(lines).strip()


def process(db: Session, payload: dict) -> dict:
    mid = payload.get("MessageID") or _header(payload, "Message-ID")
    if not mid:
        return {"status": "ignored", "reason": "sans Message-ID"}
    if db.scalars(select(InboundEmail).where(InboundEmail.message_id == mid)).first():
        return {"status": "duplicate"}
    sender = (payload.get("FromFull", {}) or {}).get("Email") or payload.get("From", "")
    sender = (re.findall(r"[\w.+-]+@[\w.-]+", sender) or [""])[0].lower()
    alias = next((r.split("@")[0] for r in _recipients(payload) if r.endswith("@" + settings.inbound_domain)), None)
    user = db.scalars(select(User).where(User.inbound_alias == alias)).first() if alias else None
    rec = InboundEmail(user_id=user.id if user else None, message_id=mid, from_addr=sender,
                       subject=(payload.get("Subject") or "")[:998], in_reply_to=_header(payload, "In-Reply-To") or None,
                       auth_ok=_auth_ok(payload), status="received")
    db.add(rec)
    db.flush()
    if not user:
        rec.status = "unknown_alias"
        db.commit()
        return {"status": rec.status}
    allowed = {user.email.lower(), *[a.lower() for a in (user.allowed_senders or [])]}
    if sender not in allowed or not rec.auth_ok:
        rec.status = "rejected_sender"  # rejet silencieux : on ne répond pas à un expéditeur inconnu
        db.commit()
        log.warning("E-mail refusé de %s pour %s", sender, alias)
        return {"status": rec.status}

    # Réponse à un dossier envoyé → message pour l'assistant
    if rec.in_reply_to:
        d = db.scalars(select(Dossier).where(Dossier.email_message_id == rec.in_reply_to,
                                             Dossier.user_id == user.id)).first()
        if d:
            text = strip_quoted(payload.get("TextBody", ""))
            d.channel, d.inbound_email_id = "email", rec.id
            if d.question and re.match(r"(?i)^\s*(oui|ok|parfait|d'accord)\b", text):
                pipeline.answer_question(db, d, "Oui, parfait")
                d.status = "ready"
                db.commit()
                from .emailer import send_dossier_reply
                send_dossier_reply(db, d)
            elif d.question and re.match(r"(?i)^\s*(original|non)\b", text):
                pipeline.answer_question(db, d, "Revenir à l'original")
            else:
                r = pipeline.apply_assistant(db, d, text, channel="email")
                if not r["changes"]:
                    send_simple_reply(sender, rec.subject, r["reply"], rec.message_id)
            rec.status = "processed"
            db.commit()
            return {"status": "assistant", "dossier_id": str(d.id)}

    # Nouvel e-mail transféré → même parcours que le dépôt web
    files = []
    for a in payload.get("Attachments", []) or []:
        try:
            files.append((a.get("Name", "piece-jointe"), base64.b64decode(a.get("Content", ""))))
        except (ValueError, TypeError):
            continue
    res = pipeline.handle_drop(db, user, files, channel="email", inbound_email_id=rec.id,
                               body_text=payload.get("TextBody", ""))
    rec.attachment_file_ids = [x["file_id"] for x in res["detected"] if x.get("file_id")]
    rec.status = "processed" if res["dossier_id"] else "no_template"
    db.commit()
    if not res["dossier_id"]:
        msg = ("Je n'ai pas trouvé de modèle de dossier (fichier Word) dans votre e-mail. "
               "Transférez l'e-mail de l'ESN avec son modèle en pièce jointe.")
        if res["profile_update_id"]:
            msg = "Votre CV a bien été reçu : votre profil est en cours de mise à jour."
        send_simple_reply(sender, rec.subject, "Bonjour,\n\n" + msg + "\n" + "\n".join(res["notes"]), rec.message_id)
    return {"status": rec.status, **res}
