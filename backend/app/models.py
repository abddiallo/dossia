"""
Modèles de données (SQLAlchemy 2.x, PostgreSQL).

  [D1] Zéro effort      : User.inbound_alias, InboundEmail, dépôt groupé
  [D2] Fidélité Word    : Template.spec (zones issues de engine.analyzer) + fidelity_report
  [D3] Zéro invention   : Dossier.segments (chaque texte avec ses faits sources) + origin_stats
  [D4] Effet réseau     : SharedTemplate (décisions + copie vidée, sans données personnelles)
  [D5] Profils tech     : compétences normalisées par engine.skills
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _updated() -> Mapped[datetime]:
    # Heure Python au moment de l'écriture (et non now() PostgreSQL = début de transaction) :
    # sinon une analyse de 30 s est datée de son début et le flux temps réel la manque.
    return mapped_column(DateTime(timezone=True), server_default=func.now(), default=_now, onupdate=_now, index=True)


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = _pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200), default="")
    plan: Mapped[str] = mapped_column(String(20), default="free")          # free | freelance | team
    inbound_alias: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    allowed_senders: Mapped[list[str]] = mapped_column(ARRAY(String(320)), default=list)
    defaults: Mapped[dict] = mapped_column(JSONB, default=dict)            # adapt, anonymize…
    created_at: Mapped[datetime] = _created()
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class StoredFile(Base):
    __tablename__ = "files"
    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30))   # cv | template | template_blank | job_posting | email | output_docx | output_pdf | preview
    filename: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(127))
    storage_key: Mapped[str] = mapped_column(String(512))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()


class Profile(Base):
    __tablename__ = "profiles"
    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(120), default="Profil principal")
    data: Mapped[dict] = mapped_column(JSONB)
    version: Mapped[int] = mapped_column(Integer, default=1)
    unverified_paths: Mapped[list[str]] = mapped_column(ARRAY(String(200)), default=list)
    source_file_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("files.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = _updated()


class ProfileUpdate(Base):
    """Nouveau CV déposé : seulement les différences, à confirmer en un clic."""
    __tablename__ = "profile_updates"
    id: Mapped[uuid.UUID] = _pk()
    profile_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    source_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(20), default="extracting")  # extracting | ready | applied | empty | failed
    method: Mapped[str | None] = mapped_column(String(20))
    diff: Mapped[dict | None] = mapped_column(JSONB)
    extracted: Mapped[dict | None] = mapped_column(JSONB)
    unverified_paths: Mapped[list[str]] = mapped_column(ARRAY(String(200)), default=list)
    error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = _updated()


class SharedTemplate(Base):
    """[D4] Connaissance partagée d'un modèle d'ESN — jamais de données du consultant d'exemple."""
    __tablename__ = "shared_templates"
    id: Mapped[uuid.UUID] = _pk()
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    esn_name: Mapped[str | None] = mapped_column(String(160), index=True)
    decisions: Mapped[dict] = mapped_column(JSONB, default=dict)
    max_pages: Mapped[int | None] = mapped_column(Integer)
    overflow_policy: Mapped[str] = mapped_column(String(30), default="keep_recent")
    blank_storage_key: Mapped[str | None] = mapped_column(String(512))
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    confirmations: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = _updated()


class Template(Base):
    __tablename__ = "templates"
    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    source_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"))
    shared_template_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("shared_templates.id", ondelete="SET NULL"))
    esn_name: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(20), default="analyzing")  # analyzing | ready | needs_answer | complex | failed
    kind: Mapped[str | None] = mapped_column(String(20))                   # blank | filled_example
    recognition_score: Mapped[float | None] = mapped_column()
    spec: Mapped[dict | None] = mapped_column(JSONB)                       # sortie de engine.analyzer
    decisions: Mapped[dict] = mapped_column(JSONB, default=dict)           # réponses de l'utilisateur
    original_pages: Mapped[int | None] = mapped_column(Integer)
    max_pages: Mapped[int | None] = mapped_column(Integer)
    overflow_policy: Mapped[str] = mapped_column(String(30), default="keep_recent")
    fidelity_report: Mapped[dict | None] = mapped_column(JSONB)
    test_preview_ids: Mapped[list[str]] = mapped_column(ARRAY(String(64)), default=list)
    source_preview_ids: Mapped[list[str] | None] = mapped_column(ARRAY(String(64)), default=list)   # pages du modèle d'origine
    from_library: Mapped[bool] = mapped_column(Boolean, default=False)
    contributed: Mapped[bool] = mapped_column(Boolean, default=False)      # déjà versé à la bibliothèque
    cleanup_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()


class JobPosting(Base):
    __tablename__ = "job_postings"
    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(20))   # upload | paste | email_body | email_attachment
    title: Mapped[str] = mapped_column(String(200), default="")
    raw_text: Mapped[str] = mapped_column(Text)
    extracted: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = _created()


class InboundEmail(Base):
    __tablename__ = "inbound_emails"
    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    message_id: Mapped[str] = mapped_column(String(512), unique=True)
    in_reply_to: Mapped[str | None] = mapped_column(String(512), index=True)
    from_addr: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(String(998), default="")
    auth_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(30))
    attachment_file_ids: Mapped[list[str]] = mapped_column(ARRAY(String(64)), default=list)
    received_at: Mapped[datetime] = _created()


class Dossier(Base):
    __tablename__ = "dossiers"
    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"))
    profile_version: Mapped[int | None] = mapped_column(Integer)
    template_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("templates.id", ondelete="CASCADE"))
    job_posting_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("job_postings.id", ondelete="SET NULL"))
    inbound_email_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("inbound_emails.id", ondelete="SET NULL"))
    channel: Mapped[str] = mapped_column(String(10), default="web")
    status: Mapped[str] = mapped_column(String(20), default="queued")   # waiting_template | queued | generating | needs_answer | ready | failed
    options: Mapped[dict] = mapped_column(JSONB, default=dict)
    options_history: Mapped[list] = mapped_column(JSONB, default=list)   # pile d'annulation
    segments: Mapped[list | None] = mapped_column(JSONB)
    view: Mapped[dict | None] = mapped_column(JSONB)
    question: Mapped[dict | None] = mapped_column(JSONB)
    origin_stats: Mapped[dict | None] = mapped_column(JSONB)
    fidelity_report: Mapped[dict | None] = mapped_column(JSONB)
    adjustments: Mapped[list] = mapped_column(JSONB, default=list)
    output_docx_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("files.id", ondelete="SET NULL"))
    output_pdf_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("files.id", ondelete="SET NULL"))
    preview_ids: Mapped[list[str]] = mapped_column(ARRAY(String(64)), default=list)
    highlight_preview_ids: Mapped[list[str] | None] = mapped_column(ARRAY(String(64)), default=list)  # aperçus surlignés
    pages: Mapped[int | None] = mapped_column(Integer)
    max_pages: Mapped[int | None] = mapped_column(Integer)
    output_filename: Mapped[str | None] = mapped_column(String(255))
    generation_ms: Mapped[int | None] = mapped_column(Integer)
    email_message_id: Mapped[str | None] = mapped_column(String(512), index=True)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _updated()

    messages: Mapped[list[AssistantMessage]] = relationship(back_populates="dossier", cascade="all, delete-orphan",
                                                            order_by="AssistantMessage.created_at")


class AssistantMessage(Base):
    __tablename__ = "assistant_messages"
    id: Mapped[uuid.UUID] = _pk()
    dossier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("dossiers.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(10))           # user | assistant
    channel: Mapped[str] = mapped_column(String(10), default="web")
    content: Mapped[str] = mapped_column(Text)
    changes: Mapped[list] = mapped_column(JSONB, default=list)
    proposal: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created()

    dossier: Mapped[Dossier] = relationship(back_populates="messages")


class UsageEvent(Base):
    __tablename__ = "usage_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    ref_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = _created()
