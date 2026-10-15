"""
Orchestration métier (base de données + moteur). Utilisé par l'API, le worker et l'e-mail entrant.

Parcours express [D1] :
  dépôt (web ou e-mail) → tri automatique → extraction du CV / analyse du modèle (tâches de fond)
  → génération dès que tout est prêt → au plus une question → téléchargement ou réponse par e-mail.
"""
from __future__ import annotations

import copy
import logging
import re
import tempfile
import uuid
from datetime import timedelta
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..config import settings
from ..db import utcnow
from ..engine import adapter, assistant as assistant_engine
from ..engine.analyzer import analyze
from ..engine.classify import classify
from ..engine.cv_extract import apply_diff, diff_is_empty, diff_profiles, extract_profile, extract_text
from ..engine.generate import generate
from ..engine.library import blank_copy, shareable_decisions
from ..engine.profile import EMPTY_PROFILE, ensure_ids
from ..engine.render import page_count, previews, to_pdf
from ..engine.text import norm
from ..models import (
    AssistantMessage, Dossier, JobPosting, Profile, ProfileUpdate, SharedTemplate, StoredFile, Template, UsageEvent, User,
)
from ..queue import enqueue
from .. import storage

log = logging.getLogger("dossia.pipeline")


# ───────────────────────────── Profil ─────────────────────────────

def get_profile(db: Session, user: User) -> Profile:
    p = db.scalars(select(Profile).where(Profile.user_id == user.id).order_by(Profile.updated_at)).first()
    if p is None:
        p = Profile(user_id=user.id, data=ensure_ids(copy.deepcopy(EMPTY_PROFILE)), version=1, unverified_paths=[])
        db.add(p)
        db.flush()
    return p


def profile_is_empty(p: Profile) -> bool:
    return not p.data.get("missions") and not p.data.get("competences")


def save_profile_data(db: Session, p: Profile, data: dict, unverified: list[str] | None = None) -> Profile:
    p.data = ensure_ids(data)
    p.version = (p.version or 1) + 1
    if unverified is not None:
        p.unverified_paths = unverified
    db.flush()
    return p


# ───────────────────────────── Dépôt unique [D1] ─────────────────────────────

def handle_drop(db: Session, user: User, files: list[tuple[str, bytes]], pasted_text: str | None = None,
                channel: str = "web", inbound_email_id: uuid.UUID | None = None, body_text: str | None = None,
                auto_dossier: bool = True, expected: str | None = None) -> dict:
    prof = get_profile(db, user)
    owner = [user.full_name, f"{prof.data['identite'].get('prenom', '')} {prof.data['identite'].get('nom', '')}".strip()]
    detected, notes = [], []
    template: Template | None = None
    posting: JobPosting | None = None
    update: ProfileUpdate | None = None

    for filename, data in files:
        ext = Path(filename).suffix.lower()
        if ext not in (".docx", ".pdf", ".txt", ".md"):
            notes.append(f"« {filename} » ignoré : formats acceptés .docx, .pdf, .txt")
            continue
        with tempfile.NamedTemporaryFile(suffix=ext, delete=True) as tmp:
            tmp.write(data)
            tmp.flush()
            try:
                text = extract_text(tmp.name)
            except Exception:  # noqa: BLE001
                text = ""
            kind, conf = classify(filename, text, owner, expected)
        log.info("Dépôt « %s » (écran : %s) → %s (%.2f)", filename, expected or "accueil", kind, conf)
        if expected == "template" and kind != "template":
            notes.append(f"« {filename} » n'est pas un fichier Word (.docx) : le modèle de l'ESN doit être en .docx.")
            continue
        if kind == "template" and ext != ".docx":
            notes.append(f"« {filename} » ressemble à un modèle mais n'est pas un fichier Word : demandez la version .docx à l'ESN.")
            kind = "unknown"
        if kind == "cv":
            f = storage.save_bytes(db, user.id, "cv", filename, data)
            update = ProfileUpdate(user_id=user.id, profile_id=prof.id, source_file_id=f.id, status="extracting")
            db.add(update)
            db.flush()
            detected.append({"file_id": str(f.id), "filename": filename, "detected_as": "cv", "confidence": conf})
        elif kind == "template":
            f = storage.save_bytes(db, user.id, "template", filename, data)
            template = Template(user_id=user.id, source_file_id=f.id, status="analyzing")
            db.add(template)
            db.flush()
            detected.append({"file_id": str(f.id), "filename": filename, "detected_as": "template", "confidence": conf,
                             "template_id": str(template.id)})
        elif kind == "job_posting":
            f = storage.save_bytes(db, user.id, "job_posting", filename, data)
            posting = create_posting(db, user, text, "email_attachment" if channel == "email" else "upload", filename)
            detected.append({"file_id": str(f.id), "filename": filename, "detected_as": "job_posting", "confidence": conf})
        else:
            detected.append({"filename": filename, "detected_as": "unknown", "confidence": conf})

    if pasted_text and pasted_text.strip():
        posting = create_posting(db, user, pasted_text, "paste")
    if posting is None and body_text and len(body_text) > 200:
        if classify("corps.txt", body_text)[0] == "job_posting":
            posting = create_posting(db, user, body_text, "email_body")
            detected.append({"filename": "corps de l'e-mail", "detected_as": "job_posting", "confidence": 0.8})

    dossier = None
    if template is not None and auto_dossier:
        dossier = Dossier(user_id=user.id, profile_id=prof.id, template_id=template.id,
                          job_posting_id=posting.id if posting else None, channel=channel,
                          inbound_email_id=inbound_email_id, status="waiting_template",
                          options={**(user.defaults or {})})
        try:
            check_quota(db, user)
        except HTTPException as e:
            dossier.status, dossier.error = "failed", e.detail
        db.add(dossier)
    elif posting is not None and not update:
        # fiche de poste seule : on la rattache au dernier dossier en attente, sinon on la garde pour le prochain
        last = db.scalars(select(Dossier).where(Dossier.user_id == user.id, Dossier.status == "waiting_template",
                                                Dossier.job_posting_id.is_(None)).order_by(Dossier.created_at.desc())).first()
        if last:
            last.job_posting_id = posting.id
    db.flush()
    db.commit()

    if update is not None:
        enqueue(job_extract_cv, str(update.id))
    if template is not None:
        enqueue(job_analyze_template, str(template.id))
    return {"detected": detected, "notes": notes,
            "profile_update_id": str(update.id) if update else None,
            "template_id": str(template.id) if template else None,
            "job_posting_id": str(posting.id) if posting else None,
            "dossier_id": str(dossier.id) if dossier else None}


def create_posting(db: Session, user: User, text: str, channel: str, title: str = "") -> JobPosting:
    info = adapter.analyze_posting(text)
    first = next((l.strip() for l in text.splitlines() if l.strip()), "")[:120]
    jp = JobPosting(user_id=user.id, channel=channel, raw_text=text[:20000], title=title or first,
                    extracted={"skills": info["skills"], "sectors": info["sectors"]})
    db.add(jp)
    db.flush()
    return jp


# ───────────────────────────── Tâches de fond ─────────────────────────────

def job_extract_cv(update_id: str) -> None:
    from ..db import session_scope
    with session_scope() as db:
        up = db.get(ProfileUpdate, uuid.UUID(update_id))
        f = db.get(StoredFile, up.source_file_id)
        user = db.get(User, up.user_id)
        prof = get_profile(db, user)
        try:
            data, unverified, method = extract_profile(storage.path_of(f))
        except Exception as e:  # noqa: BLE001
            log.exception("extraction CV")
            up.status, up.error = "failed", str(e)[:500]
            _trigger_waiting(db, user.id)
            return
        up.method, up.extracted, up.unverified_paths = method, data, unverified
        if profile_is_empty(prof):  # premier CV : appliqué directement, rien à confirmer
            save_profile_data(db, prof, data, unverified)
            prof.source_file_id = f.id
            if not user.full_name:
                user.full_name = f"{data['identite'].get('prenom', '')} {data['identite'].get('nom', '')}".strip()
            up.status, up.diff = "applied", None
        else:
            d = diff_profiles(prof.data, data)
            up.diff = d
            up.status = "empty" if diff_is_empty(d) else "ready"
        db.flush()
        _trigger_waiting(db, user.id)


def job_analyze_template(template_id: str) -> None:
    from ..db import session_scope
    with session_scope() as db:
        t = db.get(Template, uuid.UUID(template_id))
        f = db.get(StoredFile, t.source_file_id)
        src = storage.path_of(f)
        try:
            first = analyze(src, t.decisions)
            shared = db.scalars(select(SharedTemplate).where(SharedTemplate.fingerprint == first["fingerprint"])).first()
            decisions = dict(t.decisions or {})
            if shared and shared.confirmations > 0:  # [D4] modèle déjà validé par d'autres utilisateurs
                decisions = {**shared.decisions, **decisions}
                t.shared_template_id, t.from_library = shared.id, True
                t.overflow_policy = t.overflow_policy or shared.overflow_policy
                spec = analyze(src, decisions)
            else:
                spec = first
            t.spec, t.decisions = spec, decisions
            t.kind, t.recognition_score, t.status = spec["kind"], spec["recognition_score"], spec["status"]
            t.esn_name = t.esn_name or (shared.esn_name if shared else None) or spec.get("esn_name_guess") or _name_from_file(f.filename)
            if t.original_pages is None or not t.source_preview_ids:
                wd = storage.workdir("tpl", str(t.id))
                pdf = to_pdf(src, wd)
                t.original_pages = page_count(pdf)
                try:  # aperçu du modèle d'origine (écran « Nouveau modèle »)
                    pngs = previews(pdf, wd / "source", max_pages=4)
                    t.source_preview_ids = [str(storage.save_path(db, t.user_id, "preview", p, f"modele-{p.name}").id)
                                            for p in pngs]
                except Exception:  # noqa: BLE001
                    log.exception("aperçu du modèle")
            if t.max_pages is None and spec["kind"] == "filled_example":
                t.max_pages = (shared.max_pages if shared and shared.max_pages else t.original_pages)
        except Exception as e:  # noqa: BLE001
            log.exception("analyse modèle")
            t.status, t.error = "failed", "Ce fichier n'a pas pu être lu comme un modèle Word."
            for d in db.scalars(select(Dossier).where(Dossier.template_id == t.id, Dossier.status == "waiting_template")):
                d.status, d.error = "failed", t.error
            return
        db.flush()
        _trigger_waiting(db, t.user_id)
        ready = t.status == "ready"
    # Le test de fidélité tourne APRÈS : le dossier n'attend pas l'aperçu du test.
    if ready:
        enqueue(job_template_test, template_id)


def job_template_test(template_id: str) -> None:
    from ..db import session_scope
    with session_scope() as db:
        t = db.get(Template, uuid.UUID(template_id))
        try:
            run_template_test(db, t)
        except Exception:  # noqa: BLE001 — le test est informatif, il ne bloque rien
            log.exception("test de fidélité")


def _name_from_file(filename: str) -> str:
    stem = re.sub(r"(?i)(mod[eè]le|template|dossier|competences?|dc)[_\- ]*", "", Path(filename).stem)
    return re.sub(r"[_\-]+", " ", stem).strip().title() or "Modèle"


def run_template_test(db: Session, t: Template) -> None:
    """Étape « Test » automatique : génère un dossier d'essai et contrôle la fidélité. [D2]"""
    user = db.get(User, t.user_id)
    prof = get_profile(db, user)
    data = prof.data if not profile_is_empty(prof) else _demo_profile()
    spec = {**t.spec, "constraints": {**t.spec["constraints"], "max_pages": t.max_pages}}
    wd = storage.workdir("tpl", str(t.id), "test")
    r = generate(data, storage.path_of(db.get(StoredFile, t.source_file_id)), spec, {}, None, wd,
                 basename="test", overflow_policy=t.overflow_policy)
    t.fidelity_report = {**r["fidelity"], "pages": r["pages"], "max_pages": r["max_pages"], "adjustments": r["adjustments"]}
    t.test_preview_ids = [str(storage.save_path(db, t.user_id, "preview", p, f"test-{p.name}").id) for p in r["previews"]]


def _demo_profile() -> dict:
    return ensure_ids({
        **copy.deepcopy(EMPTY_PROFILE),
        "identite": {"prenom": "Camille", "nom": "Exemple", "titre": "Consultante", "annees_experience": 5,
                     "disponibilite": "", "mobilite": "", "ville": ""},
        "resume": "Profil de démonstration utilisé pour tester le modèle.",
        "competences": [{"label": "Python"}, {"label": "Git"}],
        "missions": [{"client": "Client A", "poste": "Consultante", "debut": "2022-01", "fin": None,
                      "realisations": ["Réalisation 1", "Réalisation 2"], "environnement": ["Python"]},
                     {"client": "Client B", "poste": "Consultante", "debut": "2020-01", "fin": "2021-12",
                      "realisations": ["Réalisation 1"], "environnement": ["Git"]}],
    })


WAITING = ("waiting_template", "needs_profile")
NO_PROFILE_MSG = ("Il manque votre CV : déposez-le (PDF ou Word) et le dossier se génère automatiquement.")
STALE_AFTER = timedelta(minutes=12)


def _trigger_waiting(db: Session, user_id: uuid.UUID) -> None:
    """Lance les dossiers en attente dont le modèle est prêt et le profil rempli.

    Appelée par plusieurs tâches en parallèle (lecture du CV, analyse du modèle) : chacune valide d'abord
    son propre travail, puis relit l'état validé ; le passage en « queued » est atomique, donc un dossier
    n'est lancé qu'une fois et jamais oublié.
    """
    db.commit()  # rend visible notre propre travail aux autres tâches avant de lire le leur
    db.expire_all()
    user = db.get(User, user_id)
    prof = get_profile(db, user)
    db.commit()
    extracting = db.scalar(select(func.count()).select_from(ProfileUpdate).where(
        ProfileUpdate.user_id == user_id, ProfileUpdate.status == "extracting"))
    to_launch = []
    for d in db.scalars(select(Dossier).where(Dossier.user_id == user_id, Dossier.status.in_(WAITING))).all():
        t = db.get(Template, d.template_id)
        if t is None or t.status == "failed":
            d.status, d.error = "failed", (t.error if t else None) or "Le modèle n'a pas pu être lu."
        elif t.status != "ready" or extracting:
            if d.status == "needs_profile" and extracting:
                d.status, d.error = "waiting_template", None  # un CV est en cours de lecture
        elif profile_is_empty(prof):
            if d.status != "needs_profile":
                d.status, d.error = "needs_profile", NO_PROFILE_MSG
        else:
            to_launch.append(d.id)
    db.commit()
    for did in to_launch:
        claimed = db.execute(update(Dossier).where(Dossier.id == did, Dossier.status.in_(WAITING))
                             .values(status="queued", profile_id=prof.id, error=None, updated_at=utcnow())).rowcount
        db.commit()
        if claimed:
            enqueue(job_generate, str(did))


def reconcile(db: Session, user: User) -> None:
    """Filet de sécurité appelé à la lecture : relance les dossiers bloqués (worker redémarré, tâche perdue)."""
    stale = utcnow() - STALE_AFTER
    for d in db.scalars(select(Dossier).where(Dossier.user_id == user.id, Dossier.status.in_(("queued", "generating")),
                                              Dossier.updated_at < stale)).all():
        d.status, d.error = "failed", "La génération a été interrompue. Cliquez sur Réessayer."
    for t in db.scalars(select(Template).where(Template.user_id == user.id, Template.status == "analyzing",
                                               Template.updated_at < stale)).all():
        t.status, t.error = "failed", "L'analyse du modèle a été interrompue. Déposez-le à nouveau."
    for u in db.scalars(select(ProfileUpdate).where(ProfileUpdate.user_id == user.id, ProfileUpdate.status == "extracting",
                                                    ProfileUpdate.updated_at < stale)).all():
        u.status, u.error = "failed", "La lecture du CV a été interrompue."
    _trigger_waiting(db, user.id)


def check_quota(db: Session, user: User) -> None:
    if user.plan != "free":
        return
    since = utcnow() - timedelta(days=30)
    n = db.scalar(select(func.count()).select_from(UsageEvent).where(
        UsageEvent.user_id == user.id, UsageEvent.kind == "dossier_generated", UsageEvent.created_at >= since))
    if n >= settings.free_dossiers_per_month:
        raise HTTPException(402, f"Offre gratuite : {settings.free_dossiers_per_month} dossiers par mois. "
                                 "Passez à l'offre Freelance pour un usage illimité.")


def job_generate(dossier_id: str) -> None:
    from ..db import session_scope
    with session_scope() as db:
        d = db.get(Dossier, uuid.UUID(dossier_id))
        d.status = "generating"
        db.commit()
        try:
            _generate(db, d)
        except Exception as e:  # noqa: BLE001
            log.exception("génération")
            d.status, d.error = "failed", "La génération a échoué. Réessayez ou contactez l'assistance."
            db.commit()
            return
        if d.channel == "email":
            from .emailer import send_dossier_reply
            send_dossier_reply(db, d)


def _generate(db: Session, d: Dossier) -> None:
    user = db.get(User, d.user_id)
    t = db.get(Template, d.template_id)
    prof = db.get(Profile, d.profile_id)
    jp = db.get(JobPosting, d.job_posting_id) if d.job_posting_id else None
    posting = adapter.analyze_posting(jp.raw_text) if jp else None
    opts = {**(user.defaults or {}), **(d.options or {})}
    # Reformulation IA (une seule fois, puis mise en cache dans les options) [D3]
    if posting and opts.get("adapt", True) and "rephrased" not in opts:
        targets = adapter.rephrase_targets(prof.data, posting)
        opts["rephrased"] = adapter.llm_rephrase(prof.data, posting, targets)
    spec = {**t.spec, "constraints": {**t.spec["constraints"], "max_pages": t.max_pages}}
    wd = storage.workdir("dossiers", str(d.id))
    for old in [*wd.glob("pages/*.png"), *wd.glob("hl/pages/*.png")]:
        old.unlink()
    basename = output_basename(prof.data, t, jp)
    r = generate(prof.data, storage.path_of(db.get(StoredFile, t.source_file_id)), spec, opts, posting, wd,
                 basename=basename, overflow_policy=t.overflow_policy)
    d.options = {k: v for k, v in opts.items() if k not in ("max_missions", "drop_strategy")} | (
        {"rephrased": opts.get("rephrased", {})})
    d.view, d.segments, d.origin_stats = r["view"], r["segments"], r["stats"]
    d.fidelity_report, d.adjustments = r["fidelity"], r["adjustments"]
    d.pages, d.max_pages, d.generation_ms = r["pages"], r["max_pages"], r["generation_ms"]
    d.profile_version = prof.version
    d.output_docx_id = storage.save_path(db, user.id, "output_docx", r["docx"], basename + ".docx").id
    d.output_pdf_id = storage.save_path(db, user.id, "output_pdf", r["pdf"], basename + ".pdf").id
    d.preview_ids = [str(storage.save_path(db, user.id, "preview", p, p.name).id) for p in r["previews"]]
    d.highlight_preview_ids = [str(storage.save_path(db, user.id, "preview", p, "surligne-" + p.name).id)
                               for p in r.get("highlight_previews", [])]
    d.output_filename = basename
    accepted = set(opts.get("accepted", []))
    q = r["question"]
    d.question = q if q and q["id"].split(":", 1)[-1] not in accepted else None
    d.status = "needs_answer" if d.question else "ready"
    d.error = None
    first_time = not db.scalar(select(func.count()).select_from(UsageEvent).where(
        UsageEvent.ref_id == d.id, UsageEvent.kind == "dossier_generated"))
    if first_time:
        db.add(UsageEvent(user_id=user.id, kind="dossier_generated", ref_id=d.id))
        t.usage_count = (t.usage_count or 0) + 1
        if t.shared_template_id:
            st = db.get(SharedTemplate, t.shared_template_id)
            st.usage_count += 1
    db.commit()


def output_basename(profile: dict, t: Template, jp: JobPosting | None) -> str:
    ident = profile["identite"]
    ini = "".join(x[:1] for x in (ident.get("prenom", ""), ident.get("nom", ""))).upper() or "DC"
    esn = re.sub(r"[^A-Za-z0-9]+", "", (t.esn_name or "ESN").split()[0])[:20]
    sector = ""
    if jp and jp.extracted.get("sectors"):
        sector = "_" + re.sub(r"[^A-Za-z0-9]+", "", norm(jp.extracted["sectors"][0]).title())[:15]
    return f"DC_{ini}_{esn}{sector}_{utcnow():%Y-%m}"


# ───────────────────────────── Modèles : réponses et bibliothèque [D4] ─────────────────────────────

def answer_template(db: Session, t: Template, answers: dict) -> None:
    if answers.get("missions:missing") == "support":
        t.cleanup_requested = True
        answers = {k: v for k, v in answers.items() if k != "missions:missing"}
    t.decisions = {**(t.decisions or {}), **answers}
    t.status = "analyzing"
    db.commit()
    enqueue(job_analyze_template, str(t.id))


def contribute_to_library(db: Session, t: Template) -> None:
    """Partage les décisions et une copie vidée du modèle (aucune donnée personnelle)."""
    if not t.spec or t.status != "ready" or t.contributed:
        return
    fp = t.spec["fingerprint"]
    st = db.scalars(select(SharedTemplate).where(SharedTemplate.fingerprint == fp)).first()
    if st is None:
        st = SharedTemplate(fingerprint=fp, esn_name=t.esn_name, decisions={}, usage_count=0, confirmations=0)
        db.add(st)
        db.flush()
        src = storage.path_of(db.get(StoredFile, t.source_file_id))
        dest = settings.data_dir / "_library" / f"{st.id}.docx"
        dest.parent.mkdir(parents=True, exist_ok=True)
        blank_copy(src, t.spec, dest)
        st.blank_storage_key = f"_library/{st.id}.docx"
    st.decisions = {**st.decisions, **shareable_decisions(t.spec)}
    st.esn_name = st.esn_name or t.esn_name
    st.max_pages = st.max_pages or t.max_pages
    st.overflow_policy = t.overflow_policy
    st.confirmations += 1
    t.shared_template_id = st.id
    t.contributed = True


# ───────────────────────────── Dossiers ─────────────────────────────

def create_dossier(db: Session, user: User, template: Template, posting: JobPosting | None, options: dict | None,
                   channel: str = "web") -> Dossier:
    check_quota(db, user)
    prof = get_profile(db, user)
    d = Dossier(user_id=user.id, profile_id=prof.id, template_id=template.id, channel=channel,
                job_posting_id=posting.id if posting else None, options={**(user.defaults or {}), **(options or {})},
                status="waiting_template")
    db.add(d)
    db.flush()
    db.commit()
    _trigger_waiting(db, user.id)
    db.commit()
    return d


def push_options(d: Dossier, new_options: dict) -> None:
    hist = list(d.options_history or [])
    hist.append(d.options or {})
    d.options_history = hist[-15:]
    d.options = new_options


def regenerate(db: Session, d: Dossier) -> None:
    d.status = "queued"
    db.commit()
    enqueue(job_generate, str(d.id))


def apply_assistant(db: Session, d: Dossier, message: str, channel: str = "web") -> dict:
    prof = db.get(Profile, d.profile_id)
    db.add(AssistantMessage(dossier_id=d.id, role="user", channel=channel, content=message))
    r = assistant_engine.interpret(message, prof.data, d.options or {}, d.view)
    if r["undo"]:
        ok = undo(db, d)
        reply = "C'est annulé." if ok else "Il n'y a rien à annuler."
        db.add(AssistantMessage(dossier_id=d.id, role="assistant", channel=channel, content=reply))
        db.commit()
        return {"reply": reply, "changes": [], "proposal": None}
    if r["changes"]:
        push_options(d, r["options"])
        regenerate(db, d)
    db.add(AssistantMessage(dossier_id=d.id, role="assistant", channel=channel, content=r["reply"],
                            changes=r["changes"], proposal=r["propose_profile"]))
    db.commit()
    return {"reply": r["reply"], "changes": r["changes"], "proposal": r["propose_profile"]}


def answer_question(db: Session, d: Dossier, choice: str) -> None:
    q = d.question or {}
    fid = q.get("id", ":").split(":", 1)[-1]
    o = copy.deepcopy(d.options or {})
    if norm(choice).startswith("oui"):
        o["accepted"] = sorted(set(o.get("accepted", [])) | {fid})
        push_options(d, o)
        d.question, d.status = None, "ready"
        db.commit()
        return
    o.setdefault("rephrased", {}).pop(fid, None)
    o["accepted"] = sorted(set(o.get("accepted", [])) | {fid})
    push_options(d, o)
    regenerate(db, d)


def patch_segment(db: Session, d: Dossier, key: str, final_text: str | None, decision: str | None,
                  hidden: bool | None, apply_to_profile: bool) -> None:
    seg = next((s for s in (d.segments or []) if s["key"] == key), None)
    if seg is None:
        raise HTTPException(404, "Élément introuvable")
    fid = seg["source_fact_ids"][0]
    o = copy.deepcopy(d.options or {})
    o.setdefault("overrides", {}); o.setdefault("hidden", []); o.setdefault("rephrased", {})
    if decision == "reverted":
        o["rephrased"].pop(fid, None)
        o["overrides"].pop(fid, None)
    elif decision == "accepted":
        o["accepted"] = sorted(set(o.get("accepted", [])) | {fid})
    if final_text is not None:
        key_ = fid + ".poste" if seg["field"] == "mission.poste" else fid
        o["overrides"][key_] = final_text
    if hidden is not None:
        if hidden and fid not in o["hidden"]:
            o["hidden"].append(fid)
        if not hidden and fid in o["hidden"]:
            o["hidden"].remove(fid)
    push_options(d, o)
    if apply_to_profile and final_text is not None:
        prof = db.get(Profile, d.profile_id)
        save_profile_data(db, prof, _set_fact(prof.data, fid, final_text, seg["field"]))
    regenerate(db, d)


def _set_fact(data: dict, fid: str, text: str, field: str) -> dict:
    data = copy.deepcopy(data)
    if fid == "res":
        data["resume"]["text"] = text
    elif fid.startswith("id."):
        data["identite"][fid[3:]] = text
    for m in data["missions"]:
        if fid == m["id"] and field == "mission.poste":
            m["poste"] = text
        if fid == m["contexte"]["id"]:
            m["contexte"]["text"] = text
        for r in m["realisations"]:
            if r["id"] == fid:
                r["text"] = text
    return data


def undo(db: Session, d: Dossier) -> bool:
    hist = list(d.options_history or [])
    if not hist:
        return False
    d.options = hist.pop()
    d.options_history = hist
    regenerate(db, d)
    return True
