import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.deps import get_training_service
from app.models import TrainingSession, User
from app.schemas import (
    LiveTipIn,
    LiveTipOut,
    MessageIn,
    MessageOut,
    ReportOut,
    SuggestionOut,
    TrainingSessionOut,
    TrainingStartIn,
)
from app.services.auth import current_user
from app.services.knowledge import find_relevant_knowledge
from app.services.llm import LLMClient
from app.services.training_service import TrainingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/training", tags=["training"])


def _require_session(
    db: Session,
    user: User,
    session_id: int,
    *,
    write: bool = False,
) -> TrainingSession:
    session = db.get(TrainingSession, session_id)
    if not session or session.status == "deleted":
        raise HTTPException(status_code=404, detail="训练不存在")
    allowed = TrainingService.can_write(user, session) if write else TrainingService.can_read(user, session)
    if not allowed:
        raise HTTPException(status_code=404, detail="训练不存在")
    return session


@router.post("/sessions", response_model=TrainingSessionOut)
async def start_session(
    payload: TrainingStartIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    service: TrainingService = Depends(get_training_service),
):
    return await service.start_session(db, user, payload.model_dump())


@router.get("/sessions", response_model=list[TrainingSessionOut])
def list_sessions(
    page: int | None = None,
    page_size: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """默认返回最近 100 条（兼容旧前端）；传 page/page_size 时分页。"""
    query = (
        db.query(TrainingSession)
        .filter(TrainingSession.status != "deleted")
        .order_by(TrainingSession.id.desc())
    )
    if user.role != "admin":
        query = query.filter(TrainingSession.owner_id == user.id)
    if page is not None or page_size is not None:
        page = max(1, page or 1)
        page_size = page_size if page_size and 1 <= page_size <= 100 else 20
        return query.offset((page - 1) * page_size).limit(page_size).all()
    return query.limit(100).all()


@router.delete("/sessions")
def clear_my_sessions(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    service: TrainingService = Depends(get_training_service),
):
    return {"deleted": service.clear_sessions(db, user)}


@router.get("/sessions/{session_id}", response_model=TrainingSessionOut)
def get_session(session_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return _require_session(db, user, session_id)


@router.post("/sessions/{session_id}/retry", response_model=TrainingSessionOut)
async def retry_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    service: TrainingService = Depends(get_training_service),
):
    source = _require_session(db, user, session_id)
    return await service.retry_session(db, user, source)


@router.post("/sessions/{session_id}/messages", response_model=MessageOut)
async def send_message(
    session_id: int,
    payload: MessageIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    service: TrainingService = Depends(get_training_service),
):
    session = _require_session(db, user, session_id, write=True)
    if session.status == "completed":
        raise HTTPException(status_code=400, detail="训练已完成")
    message = await service.send_message(db, session, payload.content, payload.speaker)
    return MessageOut(id=message.id, role=message.role, content=message.content, speaker=message.speaker)


@router.post("/sessions/{session_id}/stream")
async def stream_message(
    session_id: int,
    payload: MessageIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    service: TrainingService = Depends(get_training_service),
):
    """SSE 流式端点：逐 token 推送 LLM 文字，完成后流式推送 TTS 音频。"""
    session = _require_session(db, user, session_id, write=True)
    if session.status == "completed":
        raise HTTPException(status_code=400, detail="训练已完成")

    service.append_sales_message(db, session, payload.content, payload.speaker)
    db.refresh(session)

    session_snapshot = service.snapshot_session(session)
    messages_snapshot = service.snapshot_messages(session)
    knowledge = find_relevant_knowledge(db, session)
    session_id_val = session.id

    return StreamingResponse(
        service.stream_reply_events(session_id_val, session_snapshot, messages_snapshot, knowledge),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/sessions/{session_id}/suggestion", response_model=SuggestionOut)
async def suggest_reply(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    service: TrainingService = Depends(get_training_service),
):
    session = _require_session(db, user, session_id)
    if session.status == "completed":
        raise HTTPException(status_code=400, detail="训练已完成")
    result = await service.suggest_reply(db, session)
    return SuggestionOut(content=result.get("content", ""), source=result.get("source", ""))


@router.post("/sessions/{session_id}/live-tip", response_model=LiveTipOut)
async def live_tip(
    session_id: int,
    payload: LiveTipIn | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    service: TrainingService = Depends(get_training_service),
):
    """旁路实时教练：对话进行中异步取 1-2 条短提示，不阻塞主对话。"""
    session = _require_session(db, user, session_id)
    if session.status == "completed":
        raise HTTPException(status_code=400, detail="训练已完成")
    context = (payload.context if payload else "after_sales") or "after_sales"
    tips = await service.live_tip(db, session, context)
    logger.info("live-tip session=%s context=%s tips=%s", session_id, context, len(tips))
    return LiveTipOut(tips=tips)


@router.post("/sessions/{session_id}/finish", response_model=ReportOut)
async def finish_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    service: TrainingService = Depends(get_training_service),
):
    session = _require_session(db, user, session_id)
    return await service.finish_session(db, session)


@router.get("/reports/{session_id}", response_model=ReportOut)
def get_report(session_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    session = _require_session(db, user, session_id)
    if not session.report:
        raise HTTPException(status_code=404, detail="报告不存在")
    return session.report
