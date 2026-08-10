from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
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


router = APIRouter(prefix="/training", tags=["training"])


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
    db.add(TrainingMessage(session_id=session.id, role="customer", content=first_reply))
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
    db.add(TrainingMessage(session_id=session.id, role="customer", content=first_reply))
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

    db.add(TrainingMessage(session_id=session.id, role="sales", content=payload.content))
    db.commit()
    db.refresh(session)

    knowledge = find_relevant_knowledge(db, session)
    reply = await LLMClient().customer_reply(session, session.messages, knowledge)
    message = TrainingMessage(session_id=session.id, role="customer", content=reply)
    db.add(message)
    db.commit()
    db.refresh(message)
    return MessageOut(id=message.id, role=message.role, content=message.content)


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
