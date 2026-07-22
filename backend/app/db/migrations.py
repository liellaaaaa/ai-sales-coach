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

    if not statements:
        return
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
