"""报告子表 / 文档标签 双写与软删辅助。

JSON 字段保留作 API 兼容快照；明细查询走 report_scores / report_todos /
report_citations / document_tags 子表。
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import (
    DocumentTag,
    KnowledgeDocument,
    KnowledgeItem,
    ReportCitation,
    ReportScore,
    ReportTodo,
    TrainingReport,
    TrainingSession,
)


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def sync_document_tags(db: Session, document: KnowledgeDocument, tags_value: str | None = None) -> None:
    """按逗号分隔 tags 文本重建 document_tags 关联行。"""
    raw = tags_value if tags_value is not None else (document.tags or "")
    tags = [part.strip() for part in raw.replace("，", ",").split(",") if part.strip()]
    seen: set[str] = set()
    normalized: list[str] = []
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            normalized.append(tag)

    existing = {link.tag: link for link in document.tag_links}
    for tag, link in existing.items():
        if tag not in seen:
            db.delete(link)
    for tag in normalized:
        if tag not in existing:
            db.add(DocumentTag(document_id=document.id, tag=tag))
    document.tags = ",".join(normalized)


def write_report_details(db: Session, report: TrainingReport) -> None:
    """把 JSON 快照同步到 report_scores / report_todos / report_citations 子表。"""
    for rows in (report.score_rows, report.todo_rows, report.citation_rows):
        for row in list(rows):
            db.delete(row)

    scores = report.scores if isinstance(report.scores, list) else []
    for index, item in enumerate(scores):
        if not isinstance(item, dict):
            continue
        db.add(
            ReportScore(
                report_id=report.id,
                name=str(item.get("name") or ""),
                value=int(item.get("value") or 0),
                reason=str(item.get("reason") or ""),
                sort_order=index,
            )
        )

    checklist = report.checklist if isinstance(report.checklist, list) else []
    for index, item in enumerate(checklist):
        if isinstance(item, dict):
            title = str(item.get("title") or item.get("detail") or item.get("task") or "")
            detail = str(item.get("detail") or item.get("content") or item.get("task") or "")
            due = str(item.get("due") or item.get("deadline") or "")
        else:
            title = str(item or "")
            detail = ""
            due = ""
        if not title and not detail:
            continue
        db.add(
            ReportTodo(
                report_id=report.id,
                title=title or detail[:160],
                detail=detail,
                due=due,
                sort_order=index,
            )
        )

    citations = report.citations if isinstance(report.citations, list) else []
    for index, item in enumerate(citations):
        if not isinstance(item, dict):
            continue
        db.add(
            ReportCitation(
                report_id=report.id,
                source=str(item.get("source") or ""),
                reason=str(item.get("reason") or ""),
                sort_order=index,
            )
        )


def soft_delete_document(db: Session, document: KnowledgeDocument) -> None:
    now = utcnow_naive()
    document.status = "deleted"
    document.deleted_at = now
    db.query(KnowledgeItem).filter(KnowledgeItem.document_id == document.id).update(
        {"status": "deleted", "deleted_at": now}
    )
    from app.models import KnowledgeDocumentVersion

    db.query(KnowledgeDocumentVersion).filter(
        KnowledgeDocumentVersion.document_id == document.id
    ).update({"status": "disabled"})


def soft_delete_training_session(db: Session, session: TrainingSession) -> None:
    now = utcnow_naive()
    session.status = "deleted"
    session.deleted_at = now


def backfill_normalized_tables(db: Session) -> dict[str, int]:
    """把存量 JSON / 逗号 tags 回填到子表（幂等，可重复执行）。"""
    from app.models import KnowledgeDocument, TrainingReport

    stats = {"documents": 0, "reports": 0}

    for document in db.query(KnowledgeDocument).filter(KnowledgeDocument.status != "deleted").all():
        if not (document.tags or "").strip():
            continue
        has_links = db.query(DocumentTag).filter(DocumentTag.document_id == document.id).count()
        if has_links:
            continue
        sync_document_tags(db, document)
        stats["documents"] += 1

    for report in db.query(TrainingReport).all():
        has_rows = db.query(ReportScore).filter(ReportScore.report_id == report.id).count()
        if has_rows:
            continue
        write_report_details(db, report)
        stats["reports"] += 1

    db.commit()
    return stats
