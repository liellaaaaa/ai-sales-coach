from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import TrainingSession, User
from app.services.auth import current_user


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
def summary(db: Session = Depends(get_db), user: User = Depends(current_user)):
    query = db.query(TrainingSession)
    if user.role != "admin":
        query = query.filter(TrainingSession.owner_id == user.id)

    sessions = query.order_by(TrainingSession.id.desc()).all()
    reports = [item.report for item in sessions if item.report]
    avg = round(sum(item.overall_score for item in reports) / len(reports), 1) if reports else 0
    by_goal: dict[str, int] = {}
    by_stage: dict[str, int] = {}
    score_totals: dict[str, dict[str, float]] = {}
    for item in sessions:
        by_goal[item.goal] = by_goal.get(item.goal, 0) + 1
        by_stage[item.stage] = by_stage.get(item.stage, 0) + 1
        if item.report:
            score_items = item.report.scores if isinstance(item.report.scores, list) else []
            for score in score_items:
                if not isinstance(score, dict):
                    continue
                name = score.get("name")
                try:
                    value = float(score.get("value"))
                except (TypeError, ValueError):
                    continue
                bucket = score_totals.setdefault(name, {"total": 0, "count": 0})
                bucket["total"] += value
                bucket["count"] += 1
    score_averages = [
        {"name": name, "value": round(data["total"] / data["count"], 1), "count": int(data["count"])}
        for name, data in score_totals.items()
        if data["count"]
    ]
    score_averages.sort(key=lambda item: item["value"])
    completed_sessions = [item for item in sessions if item.report]
    recent_scores = [
        {
            "id": item.id,
            "goal": item.goal,
            "stage": item.stage,
            "score": item.report.overall_score,
            "date": (item.completed_at or item.created_at).isoformat(),
        }
        for item in completed_sessions[:10]
    ]
    return {
        "training_count": len(sessions),
        "completed_count": len(reports),
        "active_count": len([item for item in sessions if item.status != "completed"]),
        "average_score": avg,
        "goal_distribution": by_goal,
        "stage_distribution": by_stage,
        "score_averages": score_averages,
        "weak_dimensions": score_averages[:3],
        "strong_dimensions": sorted(score_averages, key=lambda item: item["value"], reverse=True)[:3],
        "recent_scores": list(reversed(recent_scores)),
    }
