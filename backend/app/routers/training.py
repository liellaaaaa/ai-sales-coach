import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import TrainingMessage, TrainingReport, TrainingSession, User
from app.schemas import (
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
from app.services.voice import (
    SPEAKER_DEFAULT,
    VoiceClient,
    VoiceError,
    VoiceTimeoutError,
    extract_speaker_tag,
    get_speaker_voice,
    get_tts_style,
    normalize_speaker,
)

try:
    from app.services.llm import extract_speaker
except ImportError:  # llm 侧尚未提供 extract_speaker 时的本地兜底
    extract_speaker = extract_speaker_tag

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/training", tags=["training"])


def _split_speaker(text: str) -> tuple[str, str]:
    """解析客户回复中的 speaker 标签，返回 (speaker, clean_text)。"""
    try:
        speaker, clean = extract_speaker(text or "")
    except Exception:
        return extract_speaker_tag(text or "")
    speaker = normalize_speaker(speaker)
    clean = (clean or "").strip() or (text or "").strip()
    return speaker, clean


def _can_read(user: User, session: TrainingSession) -> bool:
    if user.role == "admin":
        return True
    if session.owner_id == user.id:
        return True
    return False


@router.post("/sessions", response_model=TrainingSessionOut)
async def start_session(payload: TrainingStartIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    session = TrainingSession(owner_id=user.id, **payload.model_dump())
    db.add(session)
    db.commit()
    db.refresh(session)

    knowledge = find_relevant_knowledge(db, session)
    first_reply = await LLMClient().customer_reply(session, [], knowledge)
    speaker, clean = _split_speaker(first_reply)
    db.add(TrainingMessage(session_id=session.id, role="customer", content=clean, speaker=speaker))
    db.commit()
    db.refresh(session)
    return session


@router.get("/sessions", response_model=list[TrainingSessionOut])
def list_sessions(db: Session = Depends(get_db), user: User = Depends(current_user)):
    query = db.query(TrainingSession).order_by(TrainingSession.id.desc())
    if user.role != "admin":
        query = query.filter(TrainingSession.owner_id == user.id)
    return query.limit(100).all()


@router.delete("/sessions")
def clear_my_sessions(db: Session = Depends(get_db), user: User = Depends(current_user)):
    sessions = db.query(TrainingSession).filter(TrainingSession.owner_id == user.id).all()
    count = len(sessions)
    for session in sessions:
        db.delete(session)
    db.commit()
    return {"deleted": count}


@router.get("/sessions/{session_id}", response_model=TrainingSessionOut)
def get_session(session_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    session = db.get(TrainingSession, session_id)
    if not session or not _can_read(user, session):
        raise HTTPException(status_code=404, detail="训练不存在")
    return session


@router.post("/sessions/{session_id}/retry", response_model=TrainingSessionOut)
async def retry_session(session_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    source = db.get(TrainingSession, session_id)
    if not source or not _can_read(user, source):
        raise HTTPException(status_code=404, detail="训练不存在")

    retry_focus = ""
    if source.report:
        retry_focus = f"\n\n复训重点：{source.report.summary}"
    session = TrainingSession(
        owner_id=user.id,
        training_type=source.training_type,
        stage=source.stage,
        goal=source.goal,
        customer_name=source.customer_name,
        customer_type=source.customer_type,
        customer_difficulty=source.customer_difficulty,
        customer_personality=source.customer_personality,
        customer_concern=source.customer_concern,
        template_id=source.template_id,
        setup_context=source.setup_context or {},
        background=f"{source.background}{retry_focus}",
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    knowledge = find_relevant_knowledge(db, session)
    first_reply = await LLMClient().customer_reply(session, [], knowledge)
    speaker, clean = _split_speaker(first_reply)
    db.add(TrainingMessage(session_id=session.id, role="customer", content=clean, speaker=speaker))
    db.commit()
    db.refresh(session)
    return session


@router.post("/sessions/{session_id}/messages", response_model=MessageOut)
async def send_message(
    session_id: int,
    payload: MessageIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    session = db.get(TrainingSession, session_id)
    if not session or session.owner_id != user.id:
        raise HTTPException(status_code=404, detail="训练不存在")
    if session.status == "completed":
        raise HTTPException(status_code=400, detail="训练已完成")

    sales_speaker = normalize_speaker(payload.speaker) if payload.speaker else SPEAKER_DEFAULT
    db.add(TrainingMessage(session_id=session.id, role="sales", content=payload.content, speaker=sales_speaker))
    db.commit()
    db.refresh(session)

    knowledge = find_relevant_knowledge(db, session)
    reply = await LLMClient().customer_reply(session, session.messages, knowledge)
    speaker, clean = _split_speaker(reply)
    message = TrainingMessage(session_id=session.id, role="customer", content=clean, speaker=speaker)
    db.add(message)
    db.commit()
    db.refresh(message)
    return MessageOut(id=message.id, role=message.role, content=message.content, speaker=message.speaker)


@router.post("/sessions/{session_id}/stream")
async def stream_message(
    session_id: int,
    payload: MessageIn,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """SSE 流式端点：逐 token 推送 LLM 文字，完成后流式推送 TTS 音频。"""
    session = db.get(TrainingSession, session_id)
    if not session or session.owner_id != user.id:
        raise HTTPException(status_code=404, detail="训练不存在")
    if session.status == "completed":
        raise HTTPException(status_code=400, detail="训练已完成")

    # 在请求作用域内保存业务员消息
    sales_speaker = normalize_speaker(payload.speaker) if payload.speaker else SPEAKER_DEFAULT
    db.add(TrainingMessage(session_id=session.id, role="sales", content=payload.content, speaker=sales_speaker))
    db.commit()
    db.refresh(session)

    # 快照会话数据，避免生成器持有请求作用域的 db 对象
    session_id_val = session.id
    session_snapshot = {
        "id": session.id,
        "owner_id": session.owner_id,
        "training_type": session.training_type,
        "stage": session.stage,
        "goal": session.goal,
        "customer_name": session.customer_name,
        "customer_type": session.customer_type,
        "customer_difficulty": getattr(session, "customer_difficulty", "") or "标准",
        "customer_personality": getattr(session, "customer_personality", "") or "谨慎型",
        "customer_concern": getattr(session, "customer_concern", "") or "价格",
        "template_id": session.template_id or "",
        "background": session.background,
    }
    messages_snapshot = [
        {"role": m.role, "content": m.content, "speaker": getattr(m, "speaker", SPEAKER_DEFAULT)}
        for m in session.messages
    ]
    knowledge = find_relevant_knowledge(db, session)
    knowledge_snapshot = knowledge  # list of KnowledgeItem objects, read-only

    llm = LLMClient()
    voice = VoiceClient()

    async def event_stream():
        import base64 as _b64
        from app.db.session import SessionLocal

        gen_db = SessionLocal()
        try:
            collected_text = []

            # Phase 1: 流式推送 LLM 文字
            async for chunk in llm.customer_reply_stream(
                session_snapshot, messages_snapshot, knowledge_snapshot
            ):
                collected_text.append(chunk)
                yield f"event: token\ndata: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n"

            full_text = "".join(collected_text).strip()
            speaker, clean_text = _split_speaker(full_text)

            # 将完整回复存入数据库（使用独立会话）
            message = TrainingMessage(
                session_id=session_id_val,
                role="customer",
                content=clean_text,
                speaker=speaker,
            )
            gen_db.add(message)
            gen_db.commit()
            gen_db.refresh(message)
            yield f"event: done\ndata: {json.dumps({'id': message.id, 'content': clean_text, 'role': 'customer', 'speaker': speaker}, ensure_ascii=False)}\n\n"

            # Phase 2: 流式推送 TTS 音频（按 speaker 选音色）
            if voice.configured and clean_text:
                style = get_tts_style(
                    template_id=session_snapshot["template_id"],
                    difficulty=session_snapshot["customer_difficulty"],
                    personality=session_snapshot["customer_personality"],
                    speaker=speaker,
                )
                voice_name = get_speaker_voice(speaker)
                try:
                    async for pcm_chunk in voice.synthesize_stream(clean_text, style, voice=voice_name):
                        yield f"event: audio\ndata: {json.dumps({'data': _b64.b64encode(pcm_chunk).decode(), 'speaker': speaker}, ensure_ascii=False)}\n\n"
                except (VoiceTimeoutError, VoiceError) as exc:
                    logger.warning("TTS 流式合成失败：%s", exc)
                    yield f"event: tts_error\ndata: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"

            yield "event: complete\ndata: {}\n\n"
        except Exception as exc:
            logger.exception("流式端点异常")
            yield f"event: error\ndata: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"
            yield "event: complete\ndata: {}\n\n"
        finally:
            gen_db.close()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/sessions/{session_id}/suggestion", response_model=SuggestionOut)
async def suggest_reply(session_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    session = db.get(TrainingSession, session_id)
    if not session or session.owner_id != user.id:
        raise HTTPException(status_code=404, detail="训练不存在")
    if session.status == "completed":
        raise HTTPException(status_code=400, detail="训练已完成")
    knowledge = find_relevant_knowledge(db, session)
    content = await LLMClient().suggested_reply(session, session.messages, knowledge)
    return SuggestionOut(content=content)


@router.post("/sessions/{session_id}/finish", response_model=ReportOut)
async def finish_session(session_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    session = db.get(TrainingSession, session_id)
    if not session or session.owner_id != user.id:
        raise HTTPException(status_code=404, detail="训练不存在")
    if session.report:
        return session.report

    knowledge = find_relevant_knowledge(db, session)
    data = await LLMClient().score_report(session, session.messages, knowledge)
    report = TrainingReport(
        session_id=session.id,
        overall_score=int(data.get("overall_score", 70)),
        summary=data.get("summary", ""),
        scores=data.get("scores", []),
        good_lines=data.get("good_lines", []),
        risk_lines=data.get("risk_lines", []),
        alternatives=data.get("alternatives", []),
        checklist=data.get("checklist", []),
        citations=data.get("citations", []),
    )
    session.status = "completed"
    session.completed_at = datetime.utcnow()
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


@router.get("/reports/{session_id}", response_model=ReportOut)
def get_report(session_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    session = db.get(TrainingSession, session_id)
    if not session or not _can_read(user, session) or not session.report:
        raise HTTPException(status_code=404, detail="报告不存在")
    return session.report
