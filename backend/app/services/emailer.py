"""
E-mails sortants : lien de connexion, réponse automatique avec le dossier joint.  [D1]
Sans SMTP configuré (développement), les e-mails sont écrits dans DATA_DIR/outbox/*.eml.
"""
from __future__ import annotations

import logging
import smtplib
import uuid
from email.message import EmailMessage
from email.utils import make_msgid

from sqlalchemy.orm import Session

from ..config import settings
from ..db import utcnow
from ..models import Dossier, InboundEmail, StoredFile, Template, User
from .. import storage

log = logging.getLogger("dossia.mail")


def send(to: str, subject: str, text: str, html: str | None = None, attachments: list[tuple[str, bytes, str]] = (),
         in_reply_to: str | None = None) -> str:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.mail_from, to, subject
    mid = make_msgid(domain=settings.inbound_domain)
    msg["Message-ID"] = mid
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    for name, data, mime in attachments:
        maintype, subtype = mime.split("/", 1)
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)
    if settings.smtp_host:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as s:
            s.starttls()
            if settings.smtp_user:
                s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(msg)
    else:
        out = settings.data_dir / "outbox"
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{utcnow():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}.eml").write_bytes(bytes(msg))
        log.info("E-mail (dev) écrit dans %s : %s → %s", out, subject, to)
    return mid


def send_login_link(email: str, link: str) -> None:
    send(email, "Votre lien de connexion Dossia",
         f"Bonjour,\n\nCliquez sur ce lien pour vous connecter (valable 20 minutes) :\n{link}\n\n"
         "Si vous n'êtes pas à l'origine de cette demande, ignorez cet e-mail.\n\nDossia",
         f'<p>Bonjour,</p><p><a href="{link}" style="background:#3d6dfd;color:#fff;padding:10px 16px;'
         f'border-radius:8px;text-decoration:none">Me connecter</a></p><p style="color:#777">Lien valable 20 minutes.</p>')


def send_dossier_reply(db: Session, d: Dossier) -> None:
    user = db.get(User, d.user_id)
    t = db.get(Template, d.template_id)
    inbound = db.get(InboundEmail, d.inbound_email_id) if d.inbound_email_id else None
    to = inbound.from_addr if inbound else user.email
    esn = t.esn_name or "l'ESN"
    if d.status not in ("ready", "needs_answer"):
        send(to, f"Re: {inbound.subject if inbound else 'Votre dossier'}",
             "Bonjour,\n\nLa génération du dossier n'a pas abouti. Ouvrez Dossia pour voir le détail : "
             f"{settings.frontend_url}/dossiers/{d.id}\n\nDossia", in_reply_to=inbound.message_id if inbound else None)
        return
    files = []
    for fid, mime in ((d.output_docx_id, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
                      (d.output_pdf_id, "application/pdf")):
        if fid:
            f = db.get(StoredFile, fid)
            files.append((f.filename, storage.path_of(f).read_bytes(), mime))
    checks = []
    if d.job_posting_id:
        checks.append("Fiche de poste prise en compte : dossier adapté")
    if (d.view or {}).get("anonymized"):
        checks.append("Anonymisé")
    if d.pages:
        checks.append(f"{d.pages} page(s)" + (f" sur {d.max_pages} autorisée(s)" if d.max_pages else ""))
    checks.append("Rien d'ajouté qui ne figure pas dans votre profil")
    question = ""
    if d.question:
        question = f"\nUne question : {d.question['text']}\nRépondez « oui » ou « original » à cet e-mail.\n"
    text = (f"Bonjour,\n\nVotre dossier pour {esn} est prêt, en Word et en PDF, au format demandé par l'ESN.\n\n"
            + "\n".join(f"✓ {c}" for c in checks) + "\n" + question +
            "\nUne modification ? Répondez simplement à cet e-mail (ex. « raccourcis la synthèse »).\n"
            f"Ou ajustez-le en ligne : {settings.frontend_url}/dossiers/{d.id}\n\nDossia")
    html = (f"<p>Bonjour,</p><p>Votre dossier pour <b>{esn}</b> est prêt, en Word et en PDF, au format demandé par l'ESN.</p>"
            "<div style='background:#f4f6fa;border-radius:10px;padding:12px 16px'>"
            + "".join(f"<div>✓ {c}</div>" for c in checks) + "</div>"
            + (f"<p><b>Une question :</b> {d.question['text']}<br>Répondez « oui » ou « original » à cet e-mail.</p>" if d.question else "")
            + "<p>Une modification ? <b>Répondez simplement à cet e-mail</b> (ex. « raccourcis la synthèse »).</p>"
            f"<p><a href='{settings.frontend_url}/dossiers/{d.id}'>Ouvrir et ajuster en ligne</a></p>")
    subject = f"Re: {inbound.subject}" if inbound and inbound.subject else f"Votre dossier {esn} est prêt"
    d.email_message_id = send(to, subject, text, html, files, in_reply_to=inbound.message_id if inbound else d.email_message_id)
    db.commit()


def send_simple_reply(to: str, subject: str, text: str, in_reply_to: str | None) -> None:
    send(to, f"Re: {subject}" if subject else "Dossia", text + "\n\nDossia", in_reply_to=in_reply_to)
