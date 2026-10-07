from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.models import ReportScore, TrainingReport, TrainingSession, User
from app.services.auth import current_user


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
def summary(db: Session = Depends(get_db), user: User = Depends(current_user)):
    # SQL 聚合：不再全量拉行到内存
    base = db.query(TrainingSession).filter(TrainingSession.status != "deleted")
    if user.role != "admin":
        base = base.filter(TrainingSession.owner_id == user.id)

    training_count = base.count()
    completed_count = (
        base.filter(TrainingSession.status == "completed").count()
    )
    active_count = base.filter(TrainingSession.status == "active").count()

    avg_row = (
        db.query(func.avg(TrainingReport.overall_score))
        .join(TrainingSession, TrainingReport.session_id == TrainingSession.id)
        .filter(TrainingSession.status != "deleted")
    )
    if user.role != "admin":
        avg_row = avg_row.filter(TrainingSession.owner_id == user.id)
    avg_value = avg_row.scalar()
    avg = round(float(avg_value), 1) if avg_value is not None else 0

    def _distribution(column):
        rows = base.with_entities(column, func.count(TrainingSession.id)).group_by(column).all()
        return {str(name): int(count) for name, count in rows}

    by_goal = _distribution(TrainingSession.goal)
    by_stage = _distribution(TrainingSession.stage)

    # 维度均分：走 report_scores 子表（阶段1规范化成果）
    score_q = (
        db.query(ReportScore.name, func.avg(ReportScore.value), func.count(ReportScore.id))
        .join(TrainingReport, ReportScore.report_id == TrainingReport.id)
        .join(TrainingSession, TrainingReport.session_id == TrainingSession.id)
        .filter(TrainingSession.status != "deleted")
    )
    if user.role != "admin":
        score_q = score_q.filter(TrainingSession.owner_id == user.id)
    score_averages = [
        {"name": name, "value": round(float(avg_v), 1), "count": int(count)}
        for name, avg_v, count in score_q.group_by(ReportScore.name).all()
    ]
    score_averages.sort(key=lambda item: item["value"])

    recent_rows = (
        base.options(joinedload(TrainingSession.report))
        .filter(TrainingSession.status == "completed")
        .order_by(func.coalesce(TrainingSession.completed_at, TrainingSession.created_at).desc())
        .limit(10)
        .all()
    )
    recent_scores = [
        {
            "id": item.id,
            "goal": item.goal,
            "stage": item.stage,
            "score": item.report.overall_score if item.report else 0,
            "date": (item.completed_at or item.created_at).isoformat(),
        }
        for item in recent_rows
    ]

    return {
        "training_count": training_count,
        "completed_count": completed_count,
        "active_count": active_count,
        "average_score": avg,
        "goal_distribution": by_goal,
        "stage_distribution": by_stage,
        "score_averages": score_averages,
        "weak_dimensions": score_averages[:3],
        "strong_dimensions": sorted(score_averages, key=lambda item: item["value"], reverse=True)[:3],
        "recent_scores": list(reversed(recent_scores)),
    }


@router.get("/sessions")
def list_sessions_paged(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    query = db.query(TrainingSession).filter(TrainingSession.status != "deleted")
    if user.role != "admin":
        query = query.filter(TrainingSession.owner_id == user.id)
    total = query.count()
    items = (
        query.order_by(TrainingSession.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [
            {
                "id": item.id,
                "training_type": item.training_type,
                "stage": item.stage,
                "goal": item.goal,
                "customer_name": item.customer_name,
                "status": item.status,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
