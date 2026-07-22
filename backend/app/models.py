from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32))
    team_id: Mapped[int | None] = mapped_column(ForeignKey("teams.id"), nullable=True)
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    team: Mapped[Team | None] = relationship("Team")


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

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
    current_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class KnowledgeDocumentVersion(Base):
    __tablename__ = "knowledge_document_versions"

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class KnowledgeItem(Base):
    __tablename__ = "knowledge_items"

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
    document_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    document_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class LLMConfig(Base):
    __tablename__ = "llm_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(40), default="deepseek")
    api_key: Mapped[str] = mapped_column(Text, default="")
    base_url: Mapped[str] = mapped_column(String(255), default="https://api.deepseek.com")
    model_name: Mapped[str] = mapped_column(String(120), default="DeepSeek V4 Flash")
    model_id: Mapped[str] = mapped_column(String(120), default="deepseek-v4-flash")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TrainingSession(Base):
    __tablename__ = "training_sessions"

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    owner: Mapped[User] = relationship("User")
    messages: Mapped[list["TrainingMessage"]] = relationship(
        "TrainingMessage", cascade="all, delete-orphan", order_by="TrainingMessage.id"
    )
    report: Mapped["TrainingReport | None"] = relationship(
        "TrainingReport", cascade="all, delete-orphan", uselist=False
    )


class TrainingMessage(Base):
    __tablename__ = "training_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("training_sessions.id"))
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TrainingReport(Base):
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
