from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.models import KnowledgeItem, TrainingSession


GENERIC_VALUES = {"", "通用", "閫氱敤", "闁氨鏁?"}

GOAL_CHUNK_HINTS = {
    "价格异议": {"异议处理", "推荐话术", "禁用话术", "价值表达", "评分标准"},
    "条件谈判": {"商机推进规范", "推荐话术", "禁用话术", "关键动作"},
    "商务谈判": {"商机推进规范", "推荐话术", "禁用话术", "关键动作"},
    "技术交涉": {"产品参数", "工艺条件", "技术边界", "应用场景", "常见问题"},
    "方案论证": {"产品参数", "工艺条件", "技术边界", "应用场景", "价值表达"},
    "报告讲解": {"产品参数", "工艺条件", "价值表达", "常见问题"},
    "试样推进": {"工艺条件", "使用方法", "注意事项", "关键动作"},
    "回款交涉": {"商机推进规范", "推荐话术", "禁用话术", "风险提醒"},
    "老客维护": {"客户交涉案例", "推荐话术", "风险提醒", "关键动作"},
    "商机停滞": {"商机推进规范", "关键动作", "风险提醒", "推荐话术"},
    "首次触达": {"推荐话术", "关键动作", "客户交涉案例", "风险提醒"},
    "约到拜访": {"推荐话术", "关键动作", "商机推进规范"},
    "线索判断": {"关键动作", "商机推进规范", "风险提醒"},
}


def find_relevant_knowledge(db: Session, session: TrainingSession, limit: int = 4) -> list[KnowledgeItem]:
    items = (
        db.query(KnowledgeItem)
        .filter(KnowledgeItem.status == "active")
        .order_by(KnowledgeItem.id.desc())
        .all()
    )
    scored = [(_knowledge_score(item, session), item) for item in items]
    ranked = [item for score, item in sorted(scored, key=lambda pair: (pair[0], pair[1].id), reverse=True) if score > 0]
    if ranked:
        return ranked[:limit]
    return [item for _, item in sorted(scored, key=lambda pair: pair[1].id, reverse=True)[:limit]]


def _knowledge_score(item: KnowledgeItem, session: TrainingSession) -> int:
    score = 0
    item_stage = _clean(item.stage)
    item_scenario = _clean(item.scenario)
    item_customer = _clean(item.customer_type)
    session_stage = _clean(session.stage)
    session_goal = _clean(session.goal)
    session_customer = _clean(session.customer_type)

    if item_stage == session_stage:
        score += 8
    elif item_stage in GENERIC_VALUES:
        score += 1
    if item_scenario == session_goal:
        score += 8
    elif item_scenario in GENERIC_VALUES:
        score += 1
    if item_customer == session_customer:
        score += 4
    elif item_customer in GENERIC_VALUES:
        score += 1

    chunk_hints = _chunk_hints(session_goal, session_stage)
    if item.chunk_type in chunk_hints:
        score += 6

    haystack = " ".join(
        [
            item.title or "",
            item.source_type or "",
            item.source_name or "",
            item.chunk_type or "",
            item.section_title or "",
            item.content or "",
            item.recommended or "",
            item.banned or "",
        ]
    ).lower()
    for token in _tokens(" ".join([session.background or "", session_goal, session_stage, session_customer])):
        if token.lower() in haystack:
            score += 2
    if session_goal and session_goal in haystack:
        score += 3
    if session_stage and session_stage in haystack:
        score += 2
    score += min(3, max(0, (item.confidence or 0) - 60) // 12)
    return score


def _chunk_hints(goal: str, stage: str) -> set[str]:
    hints = set()
    for key, values in GOAL_CHUNK_HINTS.items():
        if key and (key in goal or key in stage):
            hints.update(values)
    return hints


def _tokens(text: str) -> list[str]:
    raw = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_+-]{3,}", text or "")
    stop = {"客户", "当前", "这个", "需要", "我们", "他们", "已经", "没有", "进行"}
    tokens: list[str] = []
    for token in raw:
        if token in stop or token in tokens:
            continue
        tokens.append(token)
        if len(tokens) >= 18:
            break
    return tokens


def _clean(value: str | None) -> str:
    return (value or "").strip()
