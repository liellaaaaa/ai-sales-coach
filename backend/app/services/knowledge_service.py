"""知识库文档/版本/切片编排服务。"""
from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import KnowledgeDocument, KnowledgeDocumentVersion, KnowledgeItem
from app.services.document_parser import parse_document
from app.services.report_details import soft_delete_document, sync_document_tags

DOCUMENT_TAG_PRESETS = {
    "SOP 与话术": ["销售流程", "商务谈判", "价格异议", "异议处理", "推荐话术", "禁用话术", "评分标准", "回款交涉"],
    "产品说明书": ["产品参数", "工艺条件", "应用场景", "使用方法", "注意事项", "技术边界", "价值表达", "常见问题"],
}


def document_payload(db: Session, document: KnowledgeDocument) -> dict:
    versions = (
        db.query(KnowledgeDocumentVersion)
        .filter(KnowledgeDocumentVersion.document_id == document.id)
        .order_by(KnowledgeDocumentVersion.id.desc())
        .all()
    )
    current = next((item for item in versions if item.id == document.current_version_id), None)
    return {
        "id": document.id,
        "title": document.title,
        "source_type": document.source_type,
        "source_name": document.source_name,
        "tags": document.tags,
        "purpose": document.purpose,
        "stage": document.stage,
        "scenario": document.scenario,
        "customer_type": document.customer_type,
        "recommended": document.recommended,
        "banned": document.banned,
        "parse_status": document.parse_status,
        "parse_summary": document.parse_summary,
        "error_message": document.error_message,
        "status": document.status,
        "current_version_id": document.current_version_id,
        "created_at": document.created_at,
        "current_version": current,
        "versions": versions,
    }


def next_document_version_label(db: Session, document_id: int) -> str:
    labels = (
        db.query(KnowledgeDocumentVersion.version_label)
        .filter(KnowledgeDocumentVersion.document_id == document_id)
        .all()
    )
    max_index = 0
    for (label,) in labels:
        match = re.fullmatch(r"v(\d+)", (label or "").strip().lower())
        if match:
            max_index = max(max_index, int(match.group(1)))
    return f"v{max_index + 1 if max_index else len(labels) + 1}"


def deactivate_document_chunks(db: Session, document_id: int) -> None:
    db.query(KnowledgeDocumentVersion).filter(
        KnowledgeDocumentVersion.document_id == document_id
    ).update({"status": "disabled"})
    db.query(KnowledgeItem).filter(KnowledgeItem.document_id == document_id).update(
        {"status": "disabled"}
    )


def version_source_name(document: KnowledgeDocument, version_label: str) -> str:
    return f"{document.source_name or document.title} {version_label}".strip()


def create_items_from_parsed(db: Session, document: KnowledgeDocument, version: KnowledgeDocumentVersion, parsed) -> None:
    source_name = version_source_name(document, version.version_label)
    for index, chunk in enumerate(parsed.chunks, start=1):
        db.add(
            KnowledgeItem(
                title=chunk.title or (document.title if len(parsed.chunks) == 1 else f"{document.title} #{index}"),
                source_type=document.source_type,
                source_name=source_name,
                stage=chunk.stage or document.stage,
                scenario=chunk.scenario or document.scenario,
                customer_type=document.customer_type,
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
                status="active" if parsed.parse_status == "parsed" and document.status == "active" else "disabled",
                document_id=document.id,
                document_version_id=version.id,
            )
        )


def create_document_version(
    db: Session,
    document: KnowledgeDocument,
    version_label: str,
    file_name: str,
    raw: bytes,
) -> KnowledgeDocumentVersion:
    parsed = parse_document(file_name, raw, document.source_type, document.stage, document.scenario)
    should_activate = parsed.parse_status == "parsed"
    if should_activate:
        deactivate_document_chunks(db, document.id)

    version = KnowledgeDocumentVersion(
        document_id=document.id,
        version_label=version_label,
        file_name=file_name,
        parse_status=parsed.parse_status,
        parse_summary=parsed.parse_summary,
        error_message=parsed.error_message,
        raw_text=parsed.raw_text,
        structured_data=parsed.structured_data,
        chunk_count=len(parsed.chunks),
        status="active" if should_activate else "disabled",
    )
    db.add(version)
    db.flush()

    document.parse_status = parsed.parse_status
    document.parse_summary = parsed.parse_summary
    document.error_message = parsed.error_message
    if should_activate or not document.current_version_id:
        document.current_version_id = version.id
        document.status = "active" if should_activate else "disabled"

    create_items_from_parsed(db, document, version, parsed)
    return version


def reparse_current_version(db: Session, document: KnowledgeDocument) -> bool:
    if not document.current_version_id:
        return False
    version = db.get(KnowledgeDocumentVersion, document.current_version_id)
    if not version or not version.raw_text:
        return False
    parsed = parse_document(
        version.file_name or f"{document.title}.txt",
        version.raw_text.encode("utf-8"),
        document.source_type,
        document.stage,
        document.scenario,
    )
    db.query(KnowledgeItem).filter(KnowledgeItem.document_version_id == version.id).delete()
    version.parse_status = parsed.parse_status
    version.parse_summary = parsed.parse_summary
    version.error_message = parsed.error_message
    version.structured_data = parsed.structured_data
    version.chunk_count = len(parsed.chunks)
    version.status = "active" if parsed.parse_status == "parsed" and document.status == "active" else "disabled"
    document.parse_status = parsed.parse_status
    document.parse_summary = parsed.parse_summary
    document.error_message = parsed.error_message
    create_items_from_parsed(db, document, version, parsed)
    return True


def apply_document_metadata(
    db: Session,
    document: KnowledgeDocument,
    *,
    title: str,
    source_type: str,
    tags: str,
) -> None:
    document.title = title
    document.source_name = title
    document.source_type = source_type
    document.tags = tags.strip()
    sync_document_tags(db, document, document.tags)


def soft_delete(db: Session, document: KnowledgeDocument) -> None:
    soft_delete_document(db, document)


def display_title(title: str, file_name: str) -> str:
    return (title or "").strip() or Path(file_name).stem or "未命名文档"
