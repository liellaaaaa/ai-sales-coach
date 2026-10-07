"""阶段1规范化：软删、报告子表、标签关联表、索引、外键、CHECK

Revision ID: 0002_phase1_norm
Revises: 0001_baseline
Create Date: 2026-10-26

对已存在的开发库也可执行：加列/建表/建索引均带存在性保护。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_phase1_norm"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(bind, name: str) -> bool:
    return sa.inspect(bind).has_table(name)


def _has_column(bind, table: str, column: str) -> bool:
    return any(col["name"] == column for col in sa.inspect(bind).get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()

    # 1) 软删时间戳
    for table in ("knowledge_documents", "knowledge_items", "training_sessions"):
        if _has_table(bind, table) and not _has_column(bind, table, "deleted_at"):
            op.add_column(table, sa.Column("deleted_at", sa.DateTime(), nullable=True))

    # 2) 报告明细子表（JSON 快照双写目标）
    if not _has_table(bind, "report_scores"):
        op.create_table(
            "report_scores",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("report_id", sa.Integer(), sa.ForeignKey("training_reports.id"), nullable=False),
            sa.Column("name", sa.String(length=40), nullable=False),
            sa.Column("value", sa.Integer(), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False, server_default=""),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        )
        op.create_index("ix_report_scores_report_id", "report_scores", ["report_id"])
        op.create_index("ix_report_scores_name", "report_scores", ["name"])

    if not _has_table(bind, "report_todos"):
        op.create_table(
            "report_todos",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("report_id", sa.Integer(), sa.ForeignKey("training_reports.id"), nullable=False),
            sa.Column("title", sa.String(length=160), nullable=False),
            sa.Column("detail", sa.Text(), nullable=False, server_default=""),
            sa.Column("due", sa.String(length=40), nullable=False, server_default=""),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        )
        op.create_index("ix_report_todos_report_id", "report_todos", ["report_id"])

    if not _has_table(bind, "report_citations"):
        op.create_table(
            "report_citations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("report_id", sa.Integer(), sa.ForeignKey("training_reports.id"), nullable=False),
            sa.Column("source", sa.String(length=160), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False, server_default=""),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        )
        op.create_index("ix_report_citations_report_id", "report_citations", ["report_id"])

    # 3) 文档标签关联表（1NF，替代逗号串）
    if not _has_table(bind, "document_tags"):
        op.create_table(
            "document_tags",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("document_id", sa.Integer(), sa.ForeignKey("knowledge_documents.id"), nullable=False),
            sa.Column("tag", sa.String(length=60), nullable=False),
            sa.UniqueConstraint("document_id", "tag", name="uq_document_tags_document_tag"),
        )
        op.create_index("ix_document_tags_document_id", "document_tags", ["document_id"])
        op.create_index("ix_document_tags_tag", "document_tags", ["tag"])

    # 4) 热点索引
    index_specs = [
        ("ix_training_sessions_owner_id", "training_sessions", ["owner_id"]),
        ("ix_training_sessions_status", "training_sessions", ["status"]),
        ("ix_training_sessions_created_at", "training_sessions", ["created_at"]),
        ("ix_training_messages_session_id", "training_messages", ["session_id"]),
        ("ix_knowledge_items_document_id", "knowledge_items", ["document_id"]),
        ("ix_knowledge_items_document_version_id", "knowledge_items", ["document_version_id"]),
        ("ix_knowledge_items_status", "knowledge_items", ["status"]),
        ("ix_knowledge_items_stage_scenario", "knowledge_items", ["stage", "scenario"]),
        ("ix_knowledge_documents_status", "knowledge_documents", ["status"]),
        ("ix_knowledge_documents_source_type", "knowledge_documents", ["source_type"]),
        ("ix_knowledge_documents_title", "knowledge_documents", ["title"]),
        ("ix_knowledge_document_versions_document_id", "knowledge_document_versions", ["document_id"]),
    ]
    existing_indexes = {
        ix["name"] for ix in sa.inspect(bind).get_indexes("training_sessions")
    } if _has_table(bind, "training_sessions") else set()
    # 收集全部已有索引名（跨表）
    all_index_names: set[str] = set()
    inspector = sa.inspect(bind)
    for table in inspector.get_table_names():
        for ix in inspector.get_indexes(table):
            all_index_names.add(ix["name"])
    all_index_names |= existing_indexes

    for name, table, cols in index_specs:
        if name in all_index_names:
            continue
        if not _has_table(bind, table):
            continue
        op.create_index(name, table, cols)

    # 5) 知识切片外键（PostgreSQL 直接加；SQLite 仅在新库由 create_all 建好）
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE knowledge_items ADD CONSTRAINT fk_knowledge_items_document_id "
            "FOREIGN KEY (document_id) REFERENCES knowledge_documents (id) "
            "ON DELETE SET NULL"
        )
        op.execute(
            "ALTER TABLE knowledge_items ADD CONSTRAINT fk_knowledge_items_document_version_id "
            "FOREIGN KEY (document_version_id) REFERENCES knowledge_document_versions (id) "
            "ON DELETE SET NULL"
        )

    # 6) CHECK 约束（PostgreSQL；SQLite 新库由模型 __table_args__ 建）
    if bind.dialect.name == "postgresql":
        checks = [
            ("ck_users_role", "users", "role IN ('sales', 'admin')"),
            ("ck_training_messages_role", "training_messages", "role IN ('sales', 'customer')"),
            (
                "ck_training_messages_speaker",
                "training_messages",
                "speaker IN ('buyer', 'tech', 'boss')",
            ),
            (
                "ck_training_sessions_status",
                "training_sessions",
                "status IN ('active', 'completed', 'deleted')",
            ),
            (
                "ck_knowledge_documents_status",
                "knowledge_documents",
                "status IN ('active', 'disabled', 'deleted')",
            ),
            (
                "ck_knowledge_items_status",
                "knowledge_items",
                "status IN ('active', 'disabled', 'deleted')",
            ),
        ]
        for name, table, condition in checks:
            op.execute(f'ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({condition})')


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for constraint, table in (
            ("fk_knowledge_items_document_id", "knowledge_items"),
            ("fk_knowledge_items_document_version_id", "knowledge_items"),
        ):
            op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint}")
        for name, table in (
            ("ck_users_role", "users"),
            ("ck_training_messages_role", "training_messages"),
            ("ck_training_messages_speaker", "training_messages"),
            ("ck_training_sessions_status", "training_sessions"),
            ("ck_knowledge_documents_status", "knowledge_documents"),
            ("ck_knowledge_items_status", "knowledge_items"),
        ):
            op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")

    for name, table in (
        ("ix_report_scores_report_id", "report_scores"),
        ("ix_report_scores_name", "report_scores"),
        ("ix_report_todos_report_id", "report_todos"),
        ("ix_report_citations_report_id", "report_citations"),
        ("ix_document_tags_document_id", "document_tags"),
        ("ix_document_tags_tag", "document_tags"),
        ("ix_training_sessions_owner_id", "training_sessions"),
        ("ix_training_sessions_status", "training_sessions"),
        ("ix_training_sessions_created_at", "training_sessions"),
        ("ix_training_messages_session_id", "training_messages"),
        ("ix_knowledge_items_document_id", "knowledge_items"),
        ("ix_knowledge_items_document_version_id", "knowledge_items"),
        ("ix_knowledge_items_status", "knowledge_items"),
        ("ix_knowledge_items_stage_scenario", "knowledge_items"),
        ("ix_knowledge_documents_status", "knowledge_documents"),
        ("ix_knowledge_documents_source_type", "knowledge_documents"),
        ("ix_knowledge_documents_title", "knowledge_documents"),
        ("ix_knowledge_document_versions_document_id", "knowledge_document_versions"),
    ):
        try:
            op.drop_index(name, table_name=table)
        except Exception:
            pass

    for table in ("document_tags", "report_citations", "report_todos", "report_scores"):
        op.drop_table(table)

    for table in ("knowledge_documents", "knowledge_items", "training_sessions"):
        if _has_column(bind, table, "deleted_at"):
            op.drop_column(table, "deleted_at")
