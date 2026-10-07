"""纺织助剂七维评分：权重、维度白名单、总分计算的唯一事实来源。

改权重只改这里；prompt 文案引用 DIMENSIONS / WEIGHTS。
"""
from __future__ import annotations

from typing import Any

# 维度名 → 权重（合计 1.0）
DIMENSION_WEIGHTS: dict[str, float] = {
    "工艺探询": 0.15,
    "产品选型": 0.15,
    "技术边界": 0.15,
    "异议处理": 0.15,
    "故障归因": 0.10,
    "价值合规": 0.15,
    "推进动作": 0.15,
}

DIMENSION_NAMES: tuple[str, ...] = tuple(DIMENSION_WEIGHTS.keys())
DEFAULT_WEIGHT = 0.15
SALES_TURN_SCORE_CAP = 70  # 业务员轮次 < 3 时总分上限
MIN_SALES_TURNS_FOR_FULL_SCORE = 3


def calculate_overall_score(scores: list[dict[str, Any]], sales_turns: int = MIN_SALES_TURNS_FOR_FULL_SCORE) -> int:
    """按权重计算 100 分制总分；轮次不足时封顶。"""
    if not scores or len(scores) < len(DIMENSION_NAMES):
        return 70

    weighted_sum = 0.0
    total_weight = 0.0
    for score_item in scores:
        name = score_item.get("name", "") if isinstance(score_item, dict) else ""
        value = score_item.get("value", 3) if isinstance(score_item, dict) else 3
        try:
            value_num = float(value)
        except (TypeError, ValueError):
            value_num = 3.0
        weight = DIMENSION_WEIGHTS.get(name, DEFAULT_WEIGHT)
        weighted_sum += value_num * weight
        total_weight += weight

    avg_score = weighted_sum / total_weight if total_weight > 0 else 3.0
    overall_score = int(round(avg_score * 20))
    if sales_turns < MIN_SALES_TURNS_FOR_FULL_SCORE:
        overall_score = min(overall_score, SALES_TURN_SCORE_CAP)
    return max(0, min(100, overall_score))


def normalize_score_item(item: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    """校验 LLM 回传的评分维度，非法名回退，保证七维齐全。"""
    if not isinstance(item, dict):
        return dict(fallback)
    name = item.get("name") if isinstance(item.get("name"), str) else ""
    if name not in DIMENSION_WEIGHTS:
        name = fallback.get("name", DIMENSION_NAMES[0])
    try:
        value = int(item.get("value"))
    except (TypeError, ValueError):
        value = fallback.get("value", 3)
    value = max(1, min(5, value))
    reason = item.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        reason = fallback.get("reason", "")
    return {"name": name, "value": value, "reason": reason.strip()}


def _weight_label(name: str) -> str:
    return f"权重{int(DIMENSION_WEIGHTS[name] * 100)}%"


def build_scoring_criteria_text(
    sales_turns: int,
    avg_sales_length: float,
    goal: str,
    stage: str,
) -> str:
    """生成注入 prompt 的评分标准文本（权重与 DIMENSION_WEIGHTS 同源）。"""
    criteria = [
        f"### 工艺探询（{_weight_label('工艺探询')}）——望闻问切四要素：水质、水温、使用工艺（浸轧/浸渍/喷淋）、布种；测试标准（日标/国标）为加分探询项",
        "- 5分：系统问清望闻问切四要素（水质/水温/工艺/布种），并确认测试标准后收敛推荐",
        "- 4分：问清望闻问切中三项，但遗漏布种或测试标准",
        "- 3分：问了部分条件，但水质/水温/工艺中仍有两项以上未确认",
        "- 2分：几乎只报型号不问条件，或问了但不跟进确认",
        "- 1分：完全未做工艺条件探询就直接推产品",
        "",
        f"### 产品选型（{_weight_label('产品选型')}）——推荐型号是否匹配客户条件（如水质差/水温高应推高稳 831B/868 而非只推 833）",
        "- 5分：型号与水质/水温/布种/工艺高度匹配，并说明为何选这款而非竞品款",
        "- 4分：选型基本匹配，但未说明取舍理由或备选方案",
        "- 3分：推了通用款，未针对已知条件（硬水/高温/涂料布）做差异化",
        "- 2分：型号与已知条件明显不匹配（如高温高硬仍只推 833）",
        "- 1分：乱推型号，或推了与场景无关的产品",
        "",
        f"### 技术边界（{_weight_label('技术边界')}）——是否诚实说明局限（涂料/化纤难提升、大货小样差异、同浴沉淀风险），不瞎承诺",
        "- 5分：主动说明技术边界与风险，并给出可控条件（分浴、补加、测试口径）",
        "- 4分：说明了主要边界，但个别风险未点透",
        "- 3分：提到局限但含糊，或只在被追问后才承认",
        "- 2分：对涂料/化纤提升、大货小样差异、同浴等问题有夸大或含糊承诺",
        "- 1分：满口保证绝无问题，明显瞎承诺",
        "",
        f"### 异议处理（{_weight_label('异议处理')}）——能否用参数/案例/测试标准回应，而非空话",
        "- 5分：用具体参数、测试标准（日标/国标/湿摩擦级数）、案例或数据回应异议",
        "- 4分：有依据地回应，但证据不够贴合客户场景",
        "- 3分：尝试回应，但以安抚话术为主，缺硬证据",
        "- 2分：回避异议或空泛保证「没问题」",
        "- 1分：完全没有处理客户异议",
        "",
        f"### 故障归因（{_weight_label('故障归因')}）——出现客诉/斑/色变/气味时是否先归因（水质、残留、同浴、温度）再认赔",
        "- 5分：先按水质/残留/同浴/温度/工艺窗口系统归因，再定责与整改方案",
        "- 4分：做了归因但漏掉 1 个关键变量（如未查水硬度或残留）",
        "- 3分：提到可能原因但未排查路径，过早给补偿口径",
        "- 2分：跳过归因直接道歉认赔，或甩锅客户",
        "- 1分：完全没有故障分析意识",
        "",
        f"### 价值合规（{_weight_label('价值合规')}）——是否表达认证（bluesign/GOTS/OEKO-TEX/ZDHC）、省水省时、稳定性价值，而不是只谈降价",
        "- 5分：结合认证、省水省时、批次稳定/返工风险下降等价值，并与客户痛点挂钩",
        "- 4分：表达了合规或效率价值，但与客户账算得不够细",
        "- 3分：价值表达偏泛，或只谈一点价格",
        "- 2分：几乎只谈降价/折扣，无合规与效率价值",
        "- 1分：完全没有价值表达，或违反合规口径乱承诺证书",
        "",
        f"### 推进动作（{_weight_label('推进动作')}）——是否推进到试样、小样条件、工程师介入、明确下一步人/时间/条件",
        "- 5分：推进到试样/小样条件确认，明确工程师介入与下一步人、时间、条件",
        "- 4分：有明确下一步，但缺少责任人或具体小样条件",
        "- 3分：提出下一步但不够具体（如「再联系」）",
        "- 2分：下一步动作模糊或不可执行",
        "- 1分：完全没有推进动作",
        "",
        "## 本次对话统计",
        f"- 业务员轮次：{sales_turns}轮",
        f"- 平均回复长度：{avg_sales_length:.0f}字",
        f"- 训练目标：{goal}",
        f"- 商机阶段：{stage}",
    ]
    if sales_turns < MIN_SALES_TURNS_FOR_FULL_SCORE:
        criteria.extend(
            [
                "",
                "## 特殊评分要求",
                f"- 对话轮次不足{MIN_SALES_TURNS_FOR_FULL_SCORE}轮，整体评分不得超过{SALES_TURN_SCORE_CAP}分",
                "- 需要在summary中说明对话轮次不足的影响",
            ]
        )
    return "\n".join(criteria)


def build_score_formula_text() -> str:
    """评分计算规则文案，与 DIMENSION_WEIGHTS / 封顶常量同源。"""
    parts = [f"{name}×{DIMENSION_WEIGHTS[name]}" for name in DIMENSION_NAMES]
    formula = " + ".join(parts)
    return (
        f"1. overall_score = ({formula}) × 20\n"
        "2. 每个维度必须基于对话中的具体表现评分，不能使用固定分数\n"
        f"3. 如果对话轮次少于{MIN_SALES_TURNS_FOR_FULL_SCORE}轮，整体评分不得超过{SALES_TURN_SCORE_CAP}分\n"
        "4. 若业务员未问清水质、水温、使用工艺（浸轧/浸渍/喷淋）中的任意两项，工艺探询不得超过2分\n"
        "5. 若推荐型号明显不匹配客户已知条件（如水质差/水温高却只推 833 而非高稳 831B/868），产品选型不得超过2分\n"
        "6. 若对涂料/化纤难提升、大货小样差异、同浴沉淀风险等技术边界有瞎承诺，技术边界不得超过2分\n"
        "7. 如果没有明确的下一步动作（试样、小样条件、工程师介入、明确人/时间/条件），推进动作不得超过2分\n"
        "8. 如果没有引用知识库内容，价值合规或产品选型不得满分"
    )
