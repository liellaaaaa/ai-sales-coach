import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import KnowledgeDocument, KnowledgeDocumentVersion, KnowledgeItem, User
from app.schemas import KnowledgeChunkPageOut, KnowledgeDocumentOut, KnowledgeDocumentUpdateIn, KnowledgeIn, KnowledgeOut
from app.services.auth import current_user, require_roles
from app.services.document_parser import extract_text, parse_document
from app.services.llm import MiniMaxClient


router = APIRouter(prefix="/knowledge", tags=["knowledge"])

DOCUMENT_TAG_PRESETS = {
    "SOP 与话术": ["销售流程", "商务谈判", "价格异议", "异议处理", "推荐话术", "禁用话术", "评分标准", "回款交涉"],
    "产品说明书": ["产品参数", "工艺条件", "应用场景", "使用方法", "注意事项", "技术边界", "价值表达", "常见问题"],
}


def _document_payload(db: Session, document: KnowledgeDocument) -> dict:
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


def _version_source_name(document: KnowledgeDocument, version_label: str) -> str:
    return f"{document.source_name or document.title} {version_label}".strip()


def _next_document_version_label(db: Session, document_id: int) -> str:
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


def _deactivate_document_chunks(db: Session, document_id: int):
    (
        db.query(KnowledgeDocumentVersion)
        .filter(KnowledgeDocumentVersion.document_id == document_id)
        .update({"status": "disabled"})
    )
    (
        db.query(KnowledgeItem)
        .filter(KnowledgeItem.document_id == document_id)
        .update({"status": "disabled"})
    )


def _create_document_version(
    db: Session,
    document: KnowledgeDocument,
    version_label: str,
    file_name: str,
    raw: bytes,
) -> KnowledgeDocumentVersion:
    parsed = parse_document(file_name, raw, document.source_type, document.stage, document.scenario)
    should_activate = parsed.parse_status == "parsed"
    if should_activate:
        _deactivate_document_chunks(db, document.id)

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

    _create_items_from_parsed(db, document, version, parsed)
    return version


def _create_items_from_parsed(db: Session, document: KnowledgeDocument, version: KnowledgeDocumentVersion, parsed):
    source_name = _version_source_name(document, version.version_label)
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
def list_knowledge(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return db.query(KnowledgeItem).order_by(KnowledgeItem.id.desc()).all()


@router.get("/documents", response_model=list[KnowledgeDocumentOut])
def list_documents(source_type: str | None = None, db: Session = Depends(get_db), _: User = Depends(current_user)):
    query = db.query(KnowledgeDocument).order_by(KnowledgeDocument.id.desc())
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
    display_title = (title or "").strip() or Path(file_name).stem or "未命名文档"
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
        db.flush()
        label = version_label.strip() or _next_document_version_label(db, document.id)
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
    _create_document_version(db, document, label, file_name, raw)
    db.commit()
    db.refresh(document)
    return _document_payload(db, document)


@router.post("/documents/analyze")
async def analyze_document(
    source_type: str = Form("SOP 与话术"),
    file: UploadFile = File(...),
    _: User = Depends(require_roles("admin")),
):
    raw = await file.read()
    file_name = file.filename or "未命名文档.txt"
    parsed = parse_document(file_name, raw, source_type, "通用", "通用")
    fallback = _document_analysis_fallback(file_name, source_type, parsed)
    result = await MiniMaxClient().analyze_document_metadata(file_name, parsed.raw_text, fallback)
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
    document = db.get(KnowledgeDocument, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="document not found")
    raw = await file.read()
    _create_document_version(db, document, version_label, file.filename or document.title, raw)
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
    document = db.get(KnowledgeDocument, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="document not found")
    if payload.source_type not in DOCUMENT_TAG_PRESETS:
        raise HTTPException(status_code=400, detail="unsupported source type")

    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="title is required")

    document.title = title
    document.source_name = title
    document.source_type = payload.source_type
    document.tags = payload.tags.strip()

    did_reparse = False
    if payload.reparse and document.current_version_id:
        version = db.get(KnowledgeDocumentVersion, document.current_version_id)
        if version and version.raw_text:
            parsed = parse_document(version.file_name or f"{document.title}.txt", version.raw_text.encode("utf-8"), document.source_type, document.stage, document.scenario)
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
            _create_items_from_parsed(db, document, version, parsed)
            did_reparse = True

    if not did_reparse:
        version = db.get(KnowledgeDocumentVersion, document.current_version_id) if document.current_version_id else None
        source_name = _version_source_name(document, version.version_label) if version else document.title
        (
            db.query(KnowledgeItem)
            .filter(KnowledgeItem.document_id == document.id)
            .update({"source_type": document.source_type, "source_name": source_name})
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
    if not db.get(KnowledgeDocument, document_id):
        raise HTTPException(status_code=404, detail="document not found")
    page = max(1, page)
    page_size = page_size if page_size in {20, 50, 100} else 20
    query = db.query(KnowledgeItem).filter(KnowledgeItem.document_id == document_id)
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
    document = db.get(KnowledgeDocument, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="document not found")
    document.status = "disabled" if document.status == "active" else "active"
    if document.current_version_id:
        version = db.get(KnowledgeDocumentVersion, document.current_version_id)
        if version:
            version.status = document.status
        (
            db.query(KnowledgeItem)
            .filter(KnowledgeItem.document_version_id == document.current_version_id)
            .update({"status": document.status})
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
    document = db.get(KnowledgeDocument, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="document not found")
    db.query(KnowledgeItem).filter(KnowledgeItem.document_id == document_id).delete()
    db.query(KnowledgeDocumentVersion).filter(KnowledgeDocumentVersion.document_id == document_id).delete()
    db.delete(document)
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
    if not item:
        raise HTTPException(status_code=404, detail="知识条目不存在")
    item.status = "disabled" if item.status == "active" else "active"
    db.commit()
    db.refresh(item)
    return item
