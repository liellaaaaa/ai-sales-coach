from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_llm_client
from app.models import KnowledgeDocument, KnowledgeDocumentVersion, KnowledgeItem, User
from app.schemas import KnowledgeChunkPageOut, KnowledgeDocumentOut, KnowledgeDocumentUpdateIn, KnowledgeIn, KnowledgeOut
from app.services.auth import current_user, require_roles
from app.services.document_parser import extract_text, parse_document
from app.services import knowledge_service as ks
from app.services.llm import LLMClient
from app.services.report_details import soft_delete_document, sync_document_tags


router = APIRouter(prefix="/knowledge", tags=["knowledge"])

DOCUMENT_TAG_PRESETS = ks.DOCUMENT_TAG_PRESETS


def _document_payload(db: Session, document: KnowledgeDocument) -> dict:
    return ks.document_payload(db, document)


def _require_document(db: Session, document_id: int) -> KnowledgeDocument:
    document = db.get(KnowledgeDocument, document_id)
    if not document or document.status == "deleted":
        raise HTTPException(status_code=404, detail="document not found")
    return document


def _document_analysis_fallback(filename: str, source_type: str, parsed) -> dict:
    doc_kind = parsed.structured_data.get("document_kind") if parsed.structured_data else ""
    inferred_type = "产品说明书" if doc_kind == "product" else "SOP 与话术"
    chunk_types = parsed.structured_data.get("chunk_types", {}) if parsed.structured_data else {}
    presets = DOCUMENT_TAG_PRESETS.get(inferred_type, [])
    tags = [name for name in chunk_types.keys() if name in presets][:5]
    if not tags:
        tags = presets[:2]
    return {
        "source_type": inferred_type or source_type,
        "tags": tags,
        "summary": parsed.parse_summary or f"已分析 {filename} 的正文结构。",
        "parse_status": parsed.parse_status,
        "chunk_count": len(parsed.chunks),
        "chunk_types": chunk_types,
    }


@router.get("", response_model=list[KnowledgeOut])
def list_knowledge(
    page: int | None = None,
    page_size: int | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(current_user),
):
    """默认返回全部（兼容旧前端）；传 page/page_size 时分页。"""
    query = (
        db.query(KnowledgeItem)
        .filter(KnowledgeItem.status != "deleted")
        .order_by(KnowledgeItem.id.desc())
    )
    if page is not None or page_size is not None:
        page = max(1, page or 1)
        page_size = page_size if page_size and 1 <= page_size <= 200 else 50
        query = query.offset((page - 1) * page_size).limit(page_size)
    return query.all()


@router.get("/documents", response_model=list[KnowledgeDocumentOut])
def list_documents(source_type: str | None = None, db: Session = Depends(get_db), _: User = Depends(current_user)):
    query = (
        db.query(KnowledgeDocument)
        .filter(KnowledgeDocument.status != "deleted")
        .order_by(KnowledgeDocument.id.desc())
    )
    if source_type:
        query = query.filter(KnowledgeDocument.source_type == source_type)
    return [_document_payload(db, item) for item in query.all()]


@router.post("/documents", response_model=KnowledgeDocumentOut)
async def create_document(
    title: str = Form(""),
    source_type: str = Form("SOP 与话术"),
    source_name: str = Form(""),
    tags: str = Form(""),
    purpose: str = Form(""),
    version_label: str = Form(""),
    stage: str = Form("通用"),
    scenario: str = Form("通用"),
    customer_type: str = Form("通用"),
    recommended: str = Form(""),
    banned: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    raw = await file.read()
    file_name = file.filename or title or "未命名文档.txt"
    display_title = ks.display_title(title, file_name)
    document = (
        db.query(KnowledgeDocument)
        .filter(KnowledgeDocument.title == display_title, KnowledgeDocument.source_type == source_type)
        .order_by(KnowledgeDocument.id.desc())
        .first()
    )
    if document:
        document.source_name = source_name or document.source_name or display_title
        document.tags = tags or document.tags
        document.purpose = purpose or document.purpose
        document.stage = stage or document.stage
        document.scenario = scenario or document.scenario
        document.customer_type = customer_type or document.customer_type
        document.recommended = recommended or document.recommended or purpose or "根据文档内容生成可引用依据。"
        document.banned = banned or document.banned or "不要编造文档中没有的信息。"
        document.parse_status = "pending"
        document.status = "active"
        document.deleted_at = None
        db.flush()
        sync_document_tags(db, document, document.tags)
        label = version_label.strip() or ks.next_document_version_label(db, document.id)
    else:
        document = KnowledgeDocument(
            title=display_title,
            source_type=source_type,
            source_name=source_name or display_title,
            tags=tags,
            purpose=purpose,
            stage=stage,
            scenario=scenario,
            customer_type=customer_type,
            recommended=recommended or purpose or "根据文档内容生成可引用依据。",
            banned=banned or "不要编造文档中没有的信息。",
            parse_status="pending",
            status="active",
        )
        db.add(document)
        db.flush()
        label = version_label.strip() or "v1"
    ks.create_document_version(db, document, label, file_name, raw)
    sync_document_tags(db, document, document.tags)
    db.commit()
    db.refresh(document)
    return _document_payload(db, document)


@router.post("/documents/analyze")
async def analyze_document(
    source_type: str = Form("SOP 与话术"),
    file: UploadFile = File(...),
    _: User = Depends(require_roles("admin")),
    llm: LLMClient = Depends(get_llm_client),
):
    raw = await file.read()
    file_name = file.filename or "未命名文档.txt"
    parsed = parse_document(file_name, raw, source_type, "通用", "通用")
    fallback = _document_analysis_fallback(file_name, source_type, parsed)
    result = await llm.analyze_document_metadata(file_name, parsed.raw_text, fallback)
    result["file_name"] = file_name
    return result


@router.post("/documents/{document_id}/versions", response_model=KnowledgeDocumentOut)
async def create_document_version(
    document_id: int,
    version_label: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    document = _require_document(db, document_id)
    raw = await file.read()
    ks.create_document_version(db, document, version_label, file.filename or document.title, raw)
    db.commit()
    db.refresh(document)
    return _document_payload(db, document)


@router.patch("/documents/{document_id}", response_model=KnowledgeDocumentOut)
def update_document(
    document_id: int,
    payload: KnowledgeDocumentUpdateIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    document = _require_document(db, document_id)
    if payload.source_type not in DOCUMENT_TAG_PRESETS:
        raise HTTPException(status_code=400, detail="unsupported source type")
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="title is required")

    ks.apply_document_metadata(db, document, title=title, source_type=payload.source_type, tags=payload.tags)

    did_reparse = False
    if payload.reparse:
        did_reparse = ks.reparse_current_version(db, document)

    if not did_reparse:
        version = db.get(KnowledgeDocumentVersion, document.current_version_id) if document.current_version_id else None
        source_name = ks.version_source_name(document, version.version_label) if version else document.title
        db.query(KnowledgeItem).filter(KnowledgeItem.document_id == document.id).update(
            {"source_type": document.source_type, "source_name": source_name}
        )

    db.commit()
    db.refresh(document)
    return _document_payload(db, document)


@router.get("/documents/{document_id}/chunks", response_model=KnowledgeChunkPageOut)
def list_document_chunks(
    document_id: int,
    page: int = 1,
    page_size: int = 20,
    version_id: int | None = None,
    chunk_type: str | None = None,
    stage: str | None = None,
    scenario: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(current_user),
):
    _require_document(db, document_id)
    page = max(1, page)
    page_size = page_size if page_size in {20, 50, 100} else 20
    query = db.query(KnowledgeItem).filter(
        KnowledgeItem.document_id == document_id,
        KnowledgeItem.status != "deleted",
    )
    if version_id:
        query = query.filter(KnowledgeItem.document_version_id == version_id)
    if chunk_type:
        query = query.filter(KnowledgeItem.chunk_type == chunk_type)
    if stage:
        query = query.filter(KnowledgeItem.stage == stage)
    if scenario:
        query = query.filter(KnowledgeItem.scenario == scenario)
    if status:
        query = query.filter(KnowledgeItem.status == status)
    total = query.count()
    items = (
        query.order_by(KnowledgeItem.display_order.asc(), KnowledgeItem.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("/documents/{document_id}/toggle", response_model=KnowledgeDocumentOut)
def toggle_document(
    document_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    document = _require_document(db, document_id)
    document.status = "disabled" if document.status == "active" else "active"
    if document.current_version_id:
        version = db.get(KnowledgeDocumentVersion, document.current_version_id)
        if version:
            version.status = document.status
        db.query(KnowledgeItem).filter(KnowledgeItem.document_version_id == document.current_version_id).update(
            {"status": document.status}
        )
    db.commit()
    db.refresh(document)
    return _document_payload(db, document)


@router.delete("/documents/{document_id}")
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    document = _require_document(db, document_id)
    soft_delete_document(db, document)
    db.commit()
    return {"ok": True}


@router.post("", response_model=KnowledgeOut)
def create_knowledge(
    payload: KnowledgeIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    item = KnowledgeItem(**payload.model_dump(), status="active")
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.post("/upload", response_model=KnowledgeOut)
async def upload_knowledge(
    title: str = Form(...),
    source_type: str = Form(...),
    source_name: str = Form(""),
    stage: str = Form(...),
    scenario: str = Form(...),
    customer_type: str = Form("通用"),
    recommended: str = Form(...),
    banned: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    raw = await file.read()
    content = extract_text(file.filename or title, raw)
    item = KnowledgeItem(
        title=title,
        source_type=source_type,
        source_name=source_name or file.filename or title,
        stage=stage,
        scenario=scenario,
        customer_type=customer_type,
        recommended=recommended,
        banned=banned,
        content=content,
        status="active",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.post("/{item_id}/toggle", response_model=KnowledgeOut)
def toggle_knowledge(
    item_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("admin")),
):
    item = db.get(KnowledgeItem, item_id)
    if not item or item.status == "deleted":
        raise HTTPException(status_code=404, detail="知识条目不存在")
    item.status = "disabled" if item.status == "active" else "active"
    db.commit()
    db.refresh(item)
    return item
