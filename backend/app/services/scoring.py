"""纺织助剂七维评分：权重、维度白名单、总分计算的唯一事实来源。

改权重只改这里；prompt 文案引用 DIMENSIONS / WEIGHTS。
支持按训练目标 goal 调权（纺织化工业务员场景）。
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

# 维度名 → 默认权重（合计 1.0）
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
HARD_CAP_VALUE = 2  # 触发硬约束时维度分上限

# 目标别名 → 规范名（兼容旧 goal / 知识库 scenario）
_GOAL_CANONICAL: dict[str, str] = {
    "价格异议": "价格异议",
    "报价解释": "价格异议",
    "条件收口": "条件收口",
    "条件谈判": "条件收口",
    "成交推进": "条件收口",
    "商机停滞": "条件收口",
    "方案讲解": "方案讲解",
    "技术交涉": "方案讲解",
    "报告讲解": "方案讲解",
    "方案论证": "方案讲解",
    "异议应对": "异议应对",
    "技术质疑": "异议应对",
    "未通过复盘": "异议应对",
    "回款交涉": "回款交涉",
    "线索判断": "线索判断",
    "线索获取": "线索判断",
    "建立连接": "建立连接",
    "首次触达": "建立连接",
    "加微信": "建立连接",
    "约到拜访": "建立连接",
    "需求澄清": "需求澄清",
    "首次拜访": "需求澄清",
    "再次推进": "条件收口",
    "再次拜访": "条件收口",
    "关键人确认": "条件收口",
    "试样推进": "试样推进",
    "取得样品": "试样推进",
    "关系维护": "关系维护",
    "老客维护": "关系维护",
    "服务稳定": "关系维护",
    "合同签订": "合同签订",
    "交付确认": "交付确认",
    "订单交付": "交付确认",
    "责任边界": "交付确认",
    "复购推进": "复购推进",
}

# 按训练目标调权：覆盖默认权重（须合计 1.0，get_dimension_weights 会归一化兜底）
GOAL_WEIGHT_OVERRIDES: dict[str, dict[str, float]] = {
    # 报价高、要让步：重异议与价值，轻故障归因
    "价格异议": {
        "工艺探询": 0.10,
        "产品选型": 0.10,
        "技术边界": 0.10,
        "异议处理": 0.25,
        "故障归因": 0.05,
        "价值合规": 0.20,
        "推进动作": 0.20,
    },
    # 价格/账期/交期收口：重推进与异议
    "条件收口": {
        "工艺探询": 0.10,
        "产品选型": 0.10,
        "技术边界": 0.15,
        "异议处理": 0.20,
        "故障归因": 0.05,
        "价值合规": 0.15,
        "推进动作": 0.25,
    },
    # 讲工艺/方案：重探询、选型、边界
    "方案讲解": {
        "工艺探询": 0.20,
        "产品选型": 0.20,
        "技术边界": 0.20,
        "异议处理": 0.10,
        "故障归因": 0.05,
        "价值合规": 0.15,
        "推进动作": 0.10,
    },
    # 客诉/技术质疑：重归因、边界、异议
    "异议应对": {
        "工艺探询": 0.10,
        "产品选型": 0.15,
        "技术边界": 0.20,
        "异议处理": 0.25,
        "故障归因": 0.20,
        "价值合规": 0.05,
        "推进动作": 0.05,
    },
    # 催款：重推进与交涉，价值可略降
    "回款交涉": {
        "工艺探询": 0.10,
        "产品选型": 0.10,
        "技术边界": 0.10,
        "异议处理": 0.25,
        "故障归因": 0.10,
        "价值合规": 0.10,
        "推进动作": 0.25,
    },
    # 线索：先问清条件、推进触达
    "线索判断": {
        "工艺探询": 0.20,
        "产品选型": 0.10,
        "技术边界": 0.10,
        "异议处理": 0.15,
        "故障归因": 0.05,
        "价值合规": 0.15,
        "推进动作": 0.25,
    },
    "建立连接": {
        "工艺探询": 0.15,
        "产品选型": 0.10,
        "技术边界": 0.10,
        "异议处理": 0.15,
        "故障归因": 0.05,
        "价值合规": 0.15,
        "推进动作": 0.30,
    },
    # 问需求：重望闻问切
    "需求澄清": {
        "工艺探询": 0.25,
        "产品选型": 0.15,
        "技术边界": 0.15,
        "异议处理": 0.10,
        "故障归因": 0.05,
        "价值合规": 0.10,
        "推进动作": 0.20,
    },
    # 试样：条件+边界+推进
    "试样推进": {
        "工艺探询": 0.20,
        "产品选型": 0.15,
        "技术边界": 0.20,
        "异议处理": 0.05,
        "故障归因": 0.05,
        "价值合规": 0.10,
        "推进动作": 0.25,
    },
    # 老客维护/复购：关系与复购推进
    "关系维护": {
        "工艺探询": 0.10,
        "产品选型": 0.10,
        "技术边界": 0.10,
        "异议处理": 0.20,
        "故障归因": 0.15,
        "价值合规": 0.15,
        "推进动作": 0.20,
    },
    "合同签订": {
        "工艺探询": 0.05,
        "产品选型": 0.10,
        "技术边界": 0.20,
        "异议处理": 0.20,
        "故障归因": 0.05,
        "价值合规": 0.15,
        "推进动作": 0.25,
    },
    "交付确认": {
        "工艺探询": 0.10,
        "产品选型": 0.10,
        "技术边界": 0.25,
        "异议处理": 0.15,
        "故障归因": 0.10,
        "价值合规": 0.10,
        "推进动作": 0.20,
    },
    "复购推进": {
        "工艺探询": 0.10,
        "产品选型": 0.10,
        "技术边界": 0.10,
        "异议处理": 0.15,
        "故障归因": 0.15,
        "价值合规": 0.20,
        "推进动作": 0.20,
    },
}

# 推进动作硬约束：明确下一步
_NEXT_STEP_MARKERS = (
    "试样",
    "小样",
    "打样",
    "寄样",
    "工程师",
    "应用工程师",
    "约",
    "拜访",
    "下周",
    "明天",
    "后天",
    "本周",
    "时间",
    "责任人",
    "安排",
    "确认条件",
    "测试报告",
    "对比样",
    "定下来",
    "人/时间",
)


def _canonical_goal(goal: str) -> str:
    raw = (goal or "").strip()
    if not raw:
        return ""
    return _GOAL_CANONICAL.get(raw, raw)


def _normalize_weights(weights: Mapping[str, float]) -> dict[str, float]:
    """缺维度用默认权重补齐，合计归一到 1.0。"""
    merged = dict(DIMENSION_WEIGHTS)
    for name in DIMENSION_NAMES:
        if name in weights:
            try:
                merged[name] = float(weights[name])
            except (TypeError, ValueError):
                continue
    total = sum(merged[name] for name in DIMENSION_NAMES)
    if total <= 0:
        return dict(DIMENSION_WEIGHTS)
    return {name: merged[name] / total for name in DIMENSION_NAMES}


def get_dimension_weights(goal: str = "") -> dict[str, float]:
    """按训练目标返回七维权重（已归一化）；未知目标用默认权重。"""
    key = _canonical_goal(goal)
    override = GOAL_WEIGHT_OVERRIDES.get(key)
    if not override:
        return dict(DIMENSION_WEIGHTS)
    return _normalize_weights(override)


def calculate_overall_score(
    scores: list[dict[str, Any]],
    sales_turns: int = MIN_SALES_TURNS_FOR_FULL_SCORE,
    goal: str = "",
    is_opportunity: bool = False,
) -> int:
    """按（可按 goal 调整的）权重计算 100 分制总分；陪练对话轮次不足时封顶。

    商机推进方案没有多轮对话，不套用对话轮次封顶。
    """
    if not scores or len(scores) < len(DIMENSION_NAMES):
        return 70

    weights = get_dimension_weights(goal)
    weighted_sum = 0.0
    total_weight = 0.0
    for score_item in scores:
        name = score_item.get("name", "") if isinstance(score_item, dict) else ""
        value = score_item.get("value", 3) if isinstance(score_item, dict) else 3
        try:
            value_num = float(value)
        except (TypeError, ValueError):
            value_num = 3.0
        weight = weights.get(name, DEFAULT_WEIGHT)
        weighted_sum += value_num * weight
        total_weight += weight

    avg_score = weighted_sum / total_weight if total_weight > 0 else 3.0
    overall_score = int(round(avg_score * 20))
    if not is_opportunity and sales_turns < MIN_SALES_TURNS_FOR_FULL_SCORE:
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


def _sales_blob(sales_texts: Iterable[str] | None) -> str:
    return " ".join(t for t in (sales_texts or []) if t)


def _hit_any(blob: str, markers: tuple[str, ...]) -> bool:
    return any(m in blob for m in markers)


def enforce_hard_caps(
    scores: list[dict[str, Any]],
    sales_texts: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """LLM 评分后再强制硬约束（不只写在 prompt 里）。

    - 未覆盖水质/水温/使用工艺中任意两项 → 工艺探询 ≤ 2
    - 无明确下一步 → 推进动作 ≤ 2
    - 明显瞎承诺（绝无问题/百分百/保证不）→ 技术边界 ≤ 2
    """
    blob = _sales_blob(sales_texts)
    result = [dict(item) if isinstance(item, dict) else {"name": "", "value": 3, "reason": ""} for item in scores]

    # 望闻问切三类条件（水质/水温/使用工艺），同类近义词只算一项
    process_categories = (
        _hit_any(blob, ("水质", "水硬度", "硬水")),
        _hit_any(blob, ("水温",)),
        _hit_any(blob, ("浸轧", "浸渍", "喷淋")),
    )
    has_process_ask = sum(process_categories) >= 2
    has_next_step = _hit_any(blob, _NEXT_STEP_MARKERS)
    has_overpromise = _hit_any(blob, ("绝无问题", "百分百", "保证不会", "绝对不会", "肯定没问题", "零风险"))

    for item in result:
        name = item.get("name", "")
        value = item.get("value", 3)
        try:
            value = int(value)
        except (TypeError, ValueError):
            value = 3
        reason = item.get("reason", "") or ""
        capped = False
        if name == "工艺探询" and not has_process_ask and value > HARD_CAP_VALUE:
            value = HARD_CAP_VALUE
            reason = f"{reason}（硬约束：未问清水质/水温/使用工艺中任意两项，≤{HARD_CAP_VALUE}分）".strip()
            capped = True
        if name == "推进动作" and not has_next_step and value > HARD_CAP_VALUE:
            value = HARD_CAP_VALUE
            reason = f"{reason}（硬约束：无明确下一步动作，≤{HARD_CAP_VALUE}分）".strip()
            capped = True
        if name == "技术边界" and has_overpromise and value > HARD_CAP_VALUE:
            value = HARD_CAP_VALUE
            reason = f"{reason}（硬约束：存在绝对化瞎承诺表述，≤{HARD_CAP_VALUE}分）".strip()
            capped = True
        item["value"] = max(1, min(5, value))
        if capped:
            item["reason"] = reason.strip()
    return result


def _weight_label(name: str, weights: dict[str, float] | None = None) -> str:
    w = (weights or DIMENSION_WEIGHTS)[name]
    return f"权重{round(w * 100)}%"


def build_scoring_criteria_text(
    sales_turns: int,
    avg_sales_length: float,
    goal: str,
    stage: str,
    is_opportunity: bool = False,
) -> str:
    """生成注入 prompt 的评分标准文本（权重与 get_dimension_weights 同源）。

    商机推进方案无多轮对话，不注入“对话轮次不足”约束。
    """
    weights = get_dimension_weights(goal)
    if is_opportunity:
        criteria = [
            f"### 商机信息完整度（参考）——是否把阶段、关键阻碍、关键人、最近沟通结果拆成可推进动作",
            f"### 工艺探询（{_weight_label('工艺探询', weights)}）——方案是否要求补齐水质/水温/使用工艺（浸轧/浸渍/喷淋）/布种等条件",
            "- 5分：方案明确要求补齐望闻问切四要素，并绑定到试样/测试条件",
            "- 4分：要求补齐三项条件，但遗漏布种或测试标准",
            "- 3分：提到了要问条件，但没有落到具体问题",
            "- 2分：几乎不要求澄清条件就推产品",
            "- 1分：完全跳过条件确认",
            "",
            f"### 产品选型（{_weight_label('产品选型', weights)}）——推荐是否结合已知条件给出差异化型号方向",
            "- 5分：结合水质/水温/布种/工艺给出差异化选型方向和取舍理由",
            "- 4分：有选型方向，但未说明取舍",
            "- 3分：只给通用款方向",
            "- 2分：选型方向与已知条件明显不匹配",
            "- 1分：乱推型号",
            "",
            f"### 技术边界（{_weight_label('技术边界', weights)}）——是否写清局限与可控条件，避免瞎承诺",
            "- 5分：写明技术边界与风险，并给出可控条件（分浴、补加、测试口径）",
            "- 4分：写明主要边界，个别风险未点透",
            "- 3分：提到局限但含糊",
            "- 2分：有夸大或含糊承诺",
            "- 1分：满口保证绝无问题",
            "",
            f"### 异议处理（{_weight_label('异议处理', weights)}）——交涉策略是否有证据、可执行",
            "- 5分：策略绑定参数/测试标准/案例，可直接照着说",
            "- 4分：有依据，但不够贴合客户场景",
            "- 3分：策略偏安抚，缺硬证据",
            "- 2分：策略空泛",
            "- 1分：没有可执行策略",
            "",
            f"### 故障归因（{_weight_label('故障归因', weights)}）——风险里是否覆盖水质/残留/同浴/温度等归因路径",
            "- 5分：风险覆盖关键归因变量并给排查路径",
            "- 4分：覆盖主要变量，漏 1 个",
            "- 3分：只提可能原因",
            "- 2分：忽略归因风险",
            "- 1分：完全没有风险拆解",
            "",
            f"### 价值合规（{_weight_label('价值合规', weights)}）——是否用认证、省水省时、稳定性价值支撑推进",
            "- 5分：价值主张与客户痛点挂钩，并引用认证/效率/稳定性",
            "- 4分：有价值主张，账没算细",
            "- 3分：价值偏泛",
            "- 2分：几乎只谈价格",
            "- 1分：无价值表达或乱承诺证书",
            "",
            f"### 推进动作（{_weight_label('推进动作', weights)}）——是否收敛到明确的人、时间、条件",
            "- 5分：动作落到具体责任人、时间点、测试/资料条件",
            "- 4分：有下一步，缺责任人或条件",
            "- 3分：有方向但不够具体",
            "- 2分：动作模糊",
            "- 1分：没有推进动作",
            "",
            "## 本次商机信息",
            f"- 阶段：{stage}",
            f"- 目标：{goal}",
            "- 业务员填写的商机背景、关键阻碍、关键人、最近沟通结果见下方输入",
            "## 评分要求",
            "- 每个维度必须基于商机背景、阶段、关键阻碍、关键人信息评分，不能使用固定分数",
            "- overall_score 表示当前商机推进成熟度，不是对话表现分",
            "- 禁止在 summary 中写“对话轮次不足”，因为本模式没有对话轮次",
        ]
    else:
        criteria = [
            f"### 工艺探询（{_weight_label('工艺探询', weights)}）——望闻问切四要素：水质、水温、使用工艺（浸轧/浸渍/喷淋）、布种；测试标准（日标/国标）为加分探询项",
            "- 5分：系统问清望闻问切四要素（水质/水温/工艺/布种），并确认测试标准后收敛推荐",
            "- 4分：问清望闻问切中三项，但遗漏布种或测试标准",
            "- 3分：问了部分条件，但水质/水温/工艺中仍有两项以上未确认",
            "- 2分：几乎只报型号不问条件，或问了但不跟进确认",
            "- 1分：完全未做工艺条件探询就直接推产品",
            "",
            f"### 产品选型（{_weight_label('产品选型', weights)}）——推荐型号是否匹配客户条件（如水质差/水温高应推高稳 831B/868 而非只推 833）",
            "- 5分：型号与水质/水温/布种/工艺高度匹配，并说明为何选这款而非竞品款",
            "- 4分：选型基本匹配，但未说明取舍理由或备选方案",
            "- 3分：推了通用款，未针对已知条件（硬水/高温/涂料布）做差异化",
            "- 2分：型号与已知条件明显不匹配（如高温高硬仍只推 833）",
            "- 1分：乱推型号，或推了与场景无关的产品",
            "",
            f"### 技术边界（{_weight_label('技术边界', weights)}）——是否诚实说明局限（涂料/化纤难提升、大货小样差异、同浴沉淀风险），不瞎承诺",
            "- 5分：主动说明技术边界与风险，并给出可控条件（分浴、补加、测试口径）",
            "- 4分：说明了主要边界，但个别风险未点透",
            "- 3分：提到局限但含糊，或只在被追问后才承认",
            "- 2分：对涂料/化纤提升、大货小样差异、同浴等问题有夸大或含糊承诺",
            "- 1分：满口保证绝无问题，明显瞎承诺",
            "",
            f"### 异议处理（{_weight_label('异议处理', weights)}）——能否用参数/案例/测试标准回应，而非空话",
            "- 5分：用具体参数、测试标准（日标/国标/湿摩擦级数）、案例或数据回应异议",
            "- 4分：有依据地回应，但证据不够贴合客户场景",
            "- 3分：尝试回应，但以安抚话术为主，缺硬证据",
            "- 2分：回避异议或空泛保证「没问题」",
            "- 1分：完全没有处理客户异议",
            "",
            f"### 故障归因（{_weight_label('故障归因', weights)}）——出现客诉/斑/色变/气味时是否先归因（水质、残留、同浴、温度）再认赔",
            "- 5分：先按水质/残留/同浴/温度/工艺窗口系统归因，再定责与整改方案",
            "- 4分：做了归因但漏掉 1 个关键变量（如未查水硬度或残留）",
            "- 3分：提到可能原因但未排查路径，过早给补偿口径",
            "- 2分：跳过归因直接道歉认赔，或甩锅客户",
            "- 1分：完全没有故障分析意识",
            "",
            f"### 价值合规（{_weight_label('价值合规', weights)}）——是否表达认证（bluesign/GOTS/OEKO-TEX/ZDHC）、省水省时、稳定性价值，而不是只谈降价",
            "- 5分：结合认证、省水省时、批次稳定/返工风险下降等价值，并与客户痛点挂钩",
            "- 4分：表达了合规或效率价值，但与客户账算得不够细",
            "- 3分：价值表达偏泛，或只谈一点价格",
            "- 2分：几乎只谈降价/折扣，无合规与效率价值",
            "- 1分：完全没有价值表达，或违反合规口径乱承诺证书",
            "",
            f"### 推进动作（{_weight_label('推进动作', weights)}）——是否推进到试样、小样条件、工程师介入、明确下一步人/时间/条件",
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
    if goal:
        criteria.append(f"- 本次按目标「{goal}」调权后的维度权重：")
        criteria.append(
            "、".join(f"{name}{round(weights[name] * 100)}%" for name in DIMENSION_NAMES)
        )
    return "\n".join(criteria)


def build_score_formula_text(goal: str = "", is_opportunity: bool = False) -> str:
    """评分计算规则文案，与 get_dimension_weights / 封顶常量同源。"""
    weights = get_dimension_weights(goal)
    parts = [f"{name}×{weights[name]:.2f}" for name in DIMENSION_NAMES]
    formula = " + ".join(parts)
    lines = [
        f"1. overall_score = ({formula}) × 20",
        "2. 每个维度必须基于实际内容评分，不能使用固定分数",
    ]
    if not is_opportunity:
        lines.append(
            f"3. 如果对话轮次少于{MIN_SALES_TURNS_FOR_FULL_SCORE}轮，整体评分不得超过{SALES_TURN_SCORE_CAP}分"
        )
    else:
        lines.append("3. 商机推进方案没有对话轮次，禁止用对话轮次不足作为判断或 summary")
    lines.extend(
        [
            f"4. 若未要求补齐水质、水温、使用工艺（浸轧/浸渍/喷淋）中的任意两项，工艺探询不得超过{HARD_CAP_VALUE}分（代码会强制封顶）",
            f"5. 若推荐型号方向明显不匹配客户已知条件（如水质差/水温高却只推 833 而非高稳 831B/868），产品选型不得超过{HARD_CAP_VALUE}分",
            f"6. 若对涂料/化纤难提升、大货小样差异、同浴沉淀风险等技术边界有瞎承诺，技术边界不得超过{HARD_CAP_VALUE}分（代码会强制封顶）",
            f"7. 如果没有明确的下一步动作（试样、小样条件、工程师介入、明确人/时间/条件），推进动作不得超过{HARD_CAP_VALUE}分（代码会强制封顶）",
            "8. 如果没有引用知识库内容，价值合规或产品选型不得满分",
        ]
    )
    return "\n".join(lines)
