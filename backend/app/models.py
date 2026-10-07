from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def utcnow() -> datetime:
    """统一时间源：timezone-aware UTC，替代已弃用的 datetime.utcnow。"""
    return datetime.now(timezone.utc)


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('sales', 'admin')", name="ck_users_role"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32))
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    team: Mapped[Team | None] = relationship("Team")


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'disabled', 'deleted')", name="ck_knowledge_documents_status"),
        Index("ix_knowledge_documents_status", "status"),
        Index("ix_knowledge_documents_source_type", "source_type"),
        Index("ix_knowledge_documents_title", "title"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(160))
    source_type: Mapped[str] = mapped_column(String(60))
    source_name: Mapped[str] = mapped_column(String(160))
    tags: Mapped[str] = mapped_column(Text, default="")
    purpose: Mapped[str] = mapped_column(Text, default="")
    stage: Mapped[str] = mapped_column(String(80))
    scenario: Mapped[str] = mapped_column(String(80))
    customer_type: Mapped[str] = mapped_column(String(80), default="通用")
    recommended: Mapped[str] = mapped_column(Text)
    banned: Mapped[str] = mapped_column(Text, default="")
    parse_status: Mapped[str] = mapped_column(String(30), default="pending")
    parse_summary: Mapped[str] = mapped_column(Text, default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="active")
    # 指向 knowledge_document_versions 会形成循环 FK（version.document_id → document），
    # 故保持裸 Integer；一致性由 service 层维护。
    current_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    tag_links: Mapped[list["DocumentTag"]] = relationship(
        "DocumentTag", cascade="all, delete-orphan"
    )


class DocumentTag(Base):
    """文档标签关联表（1NF）：替代逗号分隔的 tags 文本，支持按标签过滤/统计。"""

    __tablename__ = "document_tags"
    __table_args__ = (
        UniqueConstraint("document_id", "tag", name="uq_document_tags_document_tag"),
        Index("ix_document_tags_tag", "tag"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("knowledge_documents.id"), index=True)
    tag: Mapped[str] = mapped_column(String(60))


class KnowledgeDocumentVersion(Base):
    __tablename__ = "knowledge_document_versions"
    __table_args__ = (
        Index("ix_knowledge_document_versions_document_id", "document_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("knowledge_documents.id"))
    version_label: Mapped[str] = mapped_column(String(40))
    file_name: Mapped[str] = mapped_column(String(180))
    parse_status: Mapped[str] = mapped_column(String(20), default="parsed")
    parse_summary: Mapped[str] = mapped_column(Text, default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    raw_text: Mapped[str] = mapped_column(Text, default="")
    structured_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class KnowledgeItem(Base):
    __tablename__ = "knowledge_items"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'disabled', 'deleted')", name="ck_knowledge_items_status"),
        Index("ix_knowledge_items_document_id", "document_id"),
        Index("ix_knowledge_items_document_version_id", "document_version_id"),
        Index("ix_knowledge_items_status", "status"),
        Index("ix_knowledge_items_stage_scenario", "stage", "scenario"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(160))
    source_type: Mapped[str] = mapped_column(String(60))
    source_name: Mapped[str] = mapped_column(String(160))
    stage: Mapped[str] = mapped_column(String(80))
    scenario: Mapped[str] = mapped_column(String(80))
    customer_type: Mapped[str] = mapped_column(String(80), default="通用")
    recommended: Mapped[str] = mapped_column(Text)
    banned: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text)
    chunk_type: Mapped[str] = mapped_column(String(60), default="知识片段")
    section_title: Mapped[str] = mapped_column(String(160), default="")
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[int] = mapped_column(Integer, default=70)
    chunk_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    embedding_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_documents.id"), nullable=True
    )
    document_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_document_versions.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class LLMConfig(Base):
    __tablename__ = "llm_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(40), default="deepseek")
    api_key: Mapped[str] = mapped_column(Text, default="")
    base_url: Mapped[str] = mapped_column(String(255), default="https://api.deepseek.com")
    model_name: Mapped[str] = mapped_column(String(120), default="DeepSeek V4 Flash")
    model_id: Mapped[str] = mapped_column(String(120), default="deepseek-v4-flash")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class TrainingSession(Base):
    __tablename__ = "training_sessions"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'completed', 'deleted')", name="ck_training_sessions_status"),
        Index("ix_training_sessions_owner_id", "owner_id"),
        Index("ix_training_sessions_status", "status"),
        Index("ix_training_sessions_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    training_type: Mapped[str] = mapped_column(String(40))
    stage: Mapped[str] = mapped_column(String(80))
    goal: Mapped[str] = mapped_column(String(80))
    customer_name: Mapped[str] = mapped_column(String(120))
    customer_type: Mapped[str] = mapped_column(String(80))
    customer_difficulty: Mapped[str] = mapped_column(String(40), default="标准")
    customer_personality: Mapped[str] = mapped_column(String(40), default="谨慎型")
    customer_concern: Mapped[str] = mapped_column(String(40), default="价格")
    template_id: Mapped[str] = mapped_column(String(80), default="")
    setup_context: Mapped[dict] = mapped_column(JSON, default=dict)
    background: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    owner: Mapped[User] = relationship("User")
    messages: Mapped[list["TrainingMessage"]] = relationship(
        "TrainingMessage", cascade="all, delete-orphan", order_by="TrainingMessage.id"
    )
    report: Mapped["TrainingReport | None"] = relationship(
        "TrainingReport", cascade="all, delete-orphan", uselist=False
    )


class TrainingMessage(Base):
    __tablename__ = "training_messages"
    __table_args__ = (
        CheckConstraint("role IN ('sales', 'customer')", name="ck_training_messages_role"),
        CheckConstraint("speaker IN ('buyer', 'tech', 'boss')", name="ck_training_messages_speaker"),
        Index("ix_training_messages_session_id", "session_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("training_sessions.id"))
    role: Mapped[str] = mapped_column(String(20))
    speaker: Mapped[str] = mapped_column(String(40), default="buyer")
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class TrainingReport(Base):
    """复盘报告主表。scores/checklist/citations 等 JSON 字段保留作 API 快照，
    明细以 report_scores / report_todos / report_citations 子表为准（双写）。"""

    __tablename__ = "training_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("training_sessions.id"), unique=True)
    overall_score: Mapped[int] = mapped_column(Integer)
    summary: Mapped[str] = mapped_column(Text)
    scores: Mapped[dict] = mapped_column(JSON)
    good_lines: Mapped[list] = mapped_column(JSON)
    risk_lines: Mapped[list] = mapped_column(JSON)
    alternatives: Mapped[list] = mapped_column(JSON)
    checklist: Mapped[list] = mapped_column(JSON)
    citations: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    score_rows: Mapped[list["ReportScore"]] = relationship(
        "ReportScore", cascade="all, delete-orphan", order_by="ReportScore.sort_order"
    )
    todo_rows: Mapped[list["ReportTodo"]] = relationship(
        "ReportTodo", cascade="all, delete-orphan", order_by="ReportTodo.sort_order"
    )
    citation_rows: Mapped[list["ReportCitation"]] = relationship(
        "ReportCitation", cascade="all, delete-orphan", order_by="ReportCitation.sort_order"
    )


class ReportScore(Base):
    __tablename__ = "report_scores"
    __table_args__ = (
        Index("ix_report_scores_report_id", "report_id"),
        Index("ix_report_scores_name", "name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("training_reports.id"))
    name: Mapped[str] = mapped_column(String(40))
    value: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class ReportTodo(Base):
    __tablename__ = "report_todos"
    __table_args__ = (Index("ix_report_todos_report_id", "report_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("training_reports.id"))
    title: Mapped[str] = mapped_column(String(160))
    detail: Mapped[str] = mapped_column(Text, default="")
    due: Mapped[str] = mapped_column(String(40), default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class ReportCitation(Base):
    __tablename__ = "report_citations"
    __table_args__ = (Index("ix_report_citations_report_id", "report_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("training_reports.id"))
    source: Mapped[str] = mapped_column(String(160))
    reason: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
