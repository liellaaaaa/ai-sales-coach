from datetime import datetime, timezone

from sqlalchemy import inspect, text

from app.db.session import engine


def ensure_runtime_schema():
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "knowledge_items" not in tables:
        return
    statements = []
    item_columns = {column["name"] for column in inspector.get_columns("knowledge_items")}
    document_columns = {column["name"] for column in inspector.get_columns("knowledge_documents")} if "knowledge_documents" in tables else set()
    version_columns = {column["name"] for column in inspector.get_columns("knowledge_document_versions")} if "knowledge_document_versions" in tables else set()
    session_columns = {column["name"] for column in inspector.get_columns("training_sessions")} if "training_sessions" in tables else set()
    message_columns = {column["name"] for column in inspector.get_columns("training_messages")} if "training_messages" in tables else set()

    for name, column_type in {
        "document_id": "INTEGER",
        "document_version_id": "INTEGER",
        "chunk_type": "VARCHAR(60) DEFAULT '知识片段'",
        "section_title": "VARCHAR(160) DEFAULT ''",
        "page_start": "INTEGER",
        "page_end": "INTEGER",
        "confidence": "INTEGER DEFAULT 70",
        "chunk_metadata": "JSON",
        "display_order": "INTEGER DEFAULT 0",
        "embedding_json": "JSON",
    }.items():
        if name not in item_columns:
            statements.append(f"ALTER TABLE knowledge_items ADD COLUMN {name} {column_type}")

    if document_columns:
        for name, column_type in {
            "tags": "TEXT DEFAULT ''",
            "purpose": "TEXT DEFAULT ''",
            "parse_status": "VARCHAR(30) DEFAULT 'parsed'",
            "parse_summary": "TEXT DEFAULT ''",
            "error_message": "TEXT DEFAULT ''",
        }.items():
            if name not in document_columns:
                statements.append(f"ALTER TABLE knowledge_documents ADD COLUMN {name} {column_type}")

    if version_columns:
        for name, column_type in {
            "parse_summary": "TEXT DEFAULT ''",
            "error_message": "TEXT DEFAULT ''",
            "raw_text": "TEXT DEFAULT ''",
            "structured_data": "JSON",
        }.items():
            if name not in version_columns:
                statements.append(f"ALTER TABLE knowledge_document_versions ADD COLUMN {name} {column_type}")

    if session_columns:
        for name, column_type in {
            "customer_difficulty": "VARCHAR(40) DEFAULT '标准'",
            "customer_personality": "VARCHAR(40) DEFAULT '谨慎型'",
            "customer_concern": "VARCHAR(40) DEFAULT '价格'",
            "template_id": "VARCHAR(80) DEFAULT ''",
            "setup_context": "JSON DEFAULT '{}'",
        }.items():
            if name not in session_columns:
                statements.append(f"ALTER TABLE training_sessions ADD COLUMN {name} {column_type}")

    if message_columns:
        for name, column_type in {
            "speaker": "VARCHAR(40) DEFAULT 'buyer'",
        }.items():
            if name not in message_columns:
                statements.append(f"ALTER TABLE training_messages ADD COLUMN {name} {column_type}")

    # 阶段0：审计时间字段
    table_column_maps = {
        "users": {"created_at": "TIMESTAMP", "updated_at": "TIMESTAMP"},
        "knowledge_documents": {"updated_at": "TIMESTAMP"},
        "knowledge_items": {"updated_at": "TIMESTAMP"},
        "training_sessions": {"updated_at": "TIMESTAMP"},
    }
    # 阶段1：软删时间戳
    table_column_maps.setdefault("knowledge_documents", {})["deleted_at"] = "TIMESTAMP"
    table_column_maps.setdefault("knowledge_items", {})["deleted_at"] = "TIMESTAMP"
    table_column_maps.setdefault("training_sessions", {})["deleted_at"] = "TIMESTAMP"
    for table_name, columns in table_column_maps.items():
        if table_name not in tables:
            continue
        existing = {column["name"] for column in inspector.get_columns(table_name)}
        for name, column_type in columns.items():
            if name not in existing:
                statements.append(f"ALTER TABLE {table_name} ADD COLUMN {name} {column_type}")

    # 阶段1：热点索引（SQLite / PostgreSQL 均支持 IF NOT EXISTS）
    index_statements = [
        "CREATE INDEX IF NOT EXISTS ix_training_sessions_owner_id ON training_sessions (owner_id)",
        "CREATE INDEX IF NOT EXISTS ix_training_sessions_status ON training_sessions (status)",
        "CREATE INDEX IF NOT EXISTS ix_training_sessions_created_at ON training_sessions (created_at)",
        "CREATE INDEX IF NOT EXISTS ix_training_messages_session_id ON training_messages (session_id)",
        "CREATE INDEX IF NOT EXISTS ix_knowledge_items_document_id ON knowledge_items (document_id)",
        "CREATE INDEX IF NOT EXISTS ix_knowledge_items_document_version_id ON knowledge_items (document_version_id)",
        "CREATE INDEX IF NOT EXISTS ix_knowledge_items_status ON knowledge_items (status)",
        "CREATE INDEX IF NOT EXISTS ix_knowledge_items_stage_scenario ON knowledge_items (stage, scenario)",
        "CREATE INDEX IF NOT EXISTS ix_knowledge_documents_status ON knowledge_documents (status)",
        "CREATE INDEX IF NOT EXISTS ix_knowledge_documents_source_type ON knowledge_documents (source_type)",
        "CREATE INDEX IF NOT EXISTS ix_knowledge_documents_title ON knowledge_documents (title)",
        "CREATE INDEX IF NOT EXISTS ix_knowledge_document_versions_document_id ON knowledge_document_versions (document_id)",
    ]

    if not statements and not index_statements:
        return
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
        for statement in index_statements:
            connection.execute(text(statement))
        # 历史行回填当前时间，避免空值（参数化 UTC 时间戳，兼容 SQLite / PostgreSQL）
        for table_name, columns in table_column_maps.items():
            if table_name not in tables:
                continue
            for name in columns:
                if name == "deleted_at":
                    continue
                connection.execute(
                    text(f"UPDATE {table_name} SET {name} = :ts WHERE {name} IS NULL"),
                    {"ts": datetime.now(timezone.utc).replace(tzinfo=None)},
                )
