"""Auto-import markdown files from the kb/ folder into the knowledge base on first startup."""
from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import KnowledgeDocument, KnowledgeDocumentVersion, KnowledgeItem
from app.services.document_parser import parse_document


KB_DIR = Path(__file__).resolve().parent.parent.parent / "kb"

# Map filename keywords to source_type and stage/scenario defaults
FILE_META: dict[str, dict[str, str]] = {
    "前处理": {
        "source_type": "产品说明书",
        "stage": "方案论证",
        "scenario": "技术交涉",
        "tags": "产品参数,工艺条件,应用场景,使用方法,技术边界",
    },
    "固色剂": {
        "source_type": "产品说明书",
        "stage": "方案论证",
        "scenario": "技术交涉",
        "tags": "产品参数,工艺条件,应用场景,注意事项",
    },
    "硅油": {
        "source_type": "产品说明书",
        "stage": "方案论证",
        "scenario": "技术交涉",
        "tags": "产品参数,应用场景,价值表达,常见问题",
    },
    "湿摩擦": {
        "source_type": "产品说明书",
        "stage": "方案论证",
        "scenario": "技术交涉",
        "tags": "产品参数,工艺条件,应用场景,注意事项",
    },
    "日化": {
        "source_type": "产品说明书",
        "stage": "方案论证",
        "scenario": "技术交涉",
        "tags": "产品参数,应用场景,价值表达,使用方法",
    },
    "后整理": {
        "source_type": "产品说明书",
        "stage": "方案论证",
        "scenario": "技术交涉",
        "tags": "产品参数,应用场景,价值表达,技术边界",
    },
}

# Title derived from first heading in the file
TITLE_MAP: dict[str, str] = {
    "前处理": "研发一部——前处理、染色及功能性产品",
    "固色剂": "研发二部——固色剂",
    "硅油": "研发三部——硅油",
    "湿摩擦": "研发四部——湿摩擦牢度提升剂",
    "日化": "研发五部——日化原料",
    "后整理": "研发六部——后整理",
}

DEFAULT_META = {
    "source_type": "产品说明书",
    "stage": "通用",
    "scenario": "通用",
    "tags": "产品参数,应用场景",
}


def _match_key(filename: str) -> str | None:
    for key in FILE_META:
        if key in filename:
            return key
    return None


def seed_kb_from_folder(db: Session) -> int:
    """Import .md files from kb/ into the knowledge base. Returns number of documents imported."""
    if not KB_DIR.is_dir():
        return 0

    existing_titles = {doc.title for doc in db.query(KnowledgeDocument.title).all()}
    md_files = sorted(KB_DIR.glob("*.md"))
    imported = 0

    for md_file in md_files:
        raw = md_file.read_bytes()
        parsed = parse_document(md_file.name, raw, "产品说明书", "通用", "通用")
        if parsed.parse_status == "empty" and not parsed.chunks:
            continue

        key = _match_key(md_file.name)
        meta = FILE_META.get(key, DEFAULT_META) if key else DEFAULT_META
        title = TITLE_MAP.get(key, md_file.stem) if key else md_file.stem

        # Skip if already imported (by title)
        if title in existing_titles:
            continue

        document = KnowledgeDocument(
            title=title,
            source_type=meta["source_type"],
            source_name=title,
            tags=meta.get("tags", ""),
            purpose=f"产品研发培训资料——{title}",
            stage=meta.get("stage", "通用"),
            scenario=meta.get("scenario", "通用"),
            customer_type="通用",
            recommended="根据产品参数、工艺条件和技术边界生成专业回复。",
            banned="不要编造文档中没有的数据或参数。",
            parse_status=parsed.parse_status,
            parse_summary=parsed.parse_summary,
            status="active",
        )
        db.add(document)
        db.flush()

        version = KnowledgeDocumentVersion(
            document_id=document.id,
            version_label="v1",
            file_name=md_file.name,
            parse_status=parsed.parse_status,
            parse_summary=parsed.parse_summary,
            raw_text=parsed.raw_text,
            structured_data=parsed.structured_data,
            chunk_count=len(parsed.chunks),
            status="active",
        )
        db.add(version)
        db.flush()

        document.current_version_id = version.id
        existing_titles.add(title)

        source_name = f"{title} v1"
        for index, chunk in enumerate(parsed.chunks, start=1):
            db.add(
                KnowledgeItem(
                    title=chunk.title or f"{title} #{index}",
                    source_type=meta["source_type"],
                    source_name=source_name,
                    stage=chunk.stage or meta.get("stage", "通用"),
                    scenario=chunk.scenario or meta.get("scenario", "通用"),
                    customer_type="通用",
                    recommended=document.recommended,
                    banned=document.banned,
                    content=chunk.content,
                    chunk_type=chunk.chunk_type,
                    section_title=chunk.section_title,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    confidence=chunk.confidence,
                    chunk_metadata=chunk.metadata,
                    display_order=index,
                    status="active",
                    document_id=document.id,
                    document_version_id=version.id,
                )
            )

        imported += 1

    if imported:
        db.commit()
    return imported
