"""baseline: 阶段1规范化前的既有表结构

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-26

仅用于从零建库；已有库请 `alembic stamp 0001_baseline` 后再 upgrade。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "teams",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False, unique=True),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=True),
        sa.Column("manager_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("source_type", sa.String(length=60), nullable=False),
        sa.Column("source_name", sa.String(length=160), nullable=False),
        sa.Column("tags", sa.Text(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("stage", sa.String(length=80), nullable=False),
        sa.Column("scenario", sa.String(length=80), nullable=False),
        sa.Column("customer_type", sa.String(length=80), nullable=False),
        sa.Column("recommended", sa.Text(), nullable=False),
        sa.Column("banned", sa.Text(), nullable=False),
        sa.Column("parse_status", sa.String(length=30), nullable=False),
        sa.Column("parse_summary", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("current_version_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "knowledge_document_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("knowledge_documents.id"), nullable=False),
        sa.Column("version_label", sa.String(length=40), nullable=False),
        sa.Column("file_name", sa.String(length=180), nullable=False),
        sa.Column("parse_status", sa.String(length=20), nullable=False),
        sa.Column("parse_summary", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("structured_data", sa.JSON(), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "knowledge_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("source_type", sa.String(length=60), nullable=False),
        sa.Column("source_name", sa.String(length=160), nullable=False),
        sa.Column("stage", sa.String(length=80), nullable=False),
        sa.Column("scenario", sa.String(length=80), nullable=False),
        sa.Column("customer_type", sa.String(length=80), nullable=False),
        sa.Column("recommended", sa.Text(), nullable=False),
        sa.Column("banned", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("chunk_type", sa.String(length=60), nullable=False),
        sa.Column("section_title", sa.String(length=160), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("chunk_metadata", sa.JSON(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("embedding_json", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=True),
        sa.Column("document_version_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "llm_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("api_key", sa.Text(), nullable=False),
        sa.Column("base_url", sa.String(length=255), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("model_id", sa.String(length=120), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "training_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("training_type", sa.String(length=40), nullable=False),
        sa.Column("stage", sa.String(length=80), nullable=False),
        sa.Column("goal", sa.String(length=80), nullable=False),
        sa.Column("customer_name", sa.String(length=120), nullable=False),
        sa.Column("customer_type", sa.String(length=80), nullable=False),
        sa.Column("customer_difficulty", sa.String(length=40), nullable=False),
        sa.Column("customer_personality", sa.String(length=40), nullable=False),
        sa.Column("customer_concern", sa.String(length=40), nullable=False),
        sa.Column("template_id", sa.String(length=80), nullable=False),
        sa.Column("setup_context", sa.JSON(), nullable=False),
        sa.Column("background", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "training_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("training_sessions.id"), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("speaker", sa.String(length=40), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "training_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("training_sessions.id"), nullable=False),
        sa.Column("overall_score", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("scores", sa.JSON(), nullable=False),
        sa.Column("good_lines", sa.JSON(), nullable=False),
        sa.Column("risk_lines", sa.JSON(), nullable=False),
        sa.Column("alternatives", sa.JSON(), nullable=False),
        sa.Column("checklist", sa.JSON(), nullable=False),
        sa.Column("citations", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("session_id"),
    )


def downgrade() -> None:
    for table in (
        "training_reports",
        "training_messages",
        "training_sessions",
        "llm_configs",
        "knowledge_items",
        "knowledge_document_versions",
        "knowledge_documents",
        "users",
        "teams",
    ):
        op.drop_table(table)
