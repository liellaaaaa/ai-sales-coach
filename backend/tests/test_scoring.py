"""scoring 模块单测：权重、goal 调权、硬约束、封顶、维度白名单。"""
from app.services.scoring import (
    DIMENSION_NAMES,
    DIMENSION_WEIGHTS,
    GOAL_WEIGHT_OVERRIDES,
    HARD_CAP_VALUE,
    SALES_TURN_SCORE_CAP,
    build_score_formula_text,
    build_scoring_criteria_text,
    calculate_overall_score,
    enforce_hard_caps,
    get_dimension_weights,
    normalize_score_item,
)


def _scores(values: dict[str, int]) -> list[dict]:
    return [{"name": name, "value": values.get(name, 3), "reason": "x"} for name in DIMENSION_NAMES]


def test_weights_sum_to_one():
    assert abs(sum(DIMENSION_WEIGHTS.values()) - 1.0) < 1e-9


def test_all_goal_overrides_sum_to_one():
    for goal, weights in GOAL_WEIGHT_OVERRIDES.items():
        assert abs(sum(weights.values()) - 1.0) < 1e-9, goal
        assert set(weights.keys()) == set(DIMENSION_NAMES), goal
        normalized = get_dimension_weights(goal)
        assert abs(sum(normalized.values()) - 1.0) < 1e-9, goal
        assert set(normalized.keys()) == set(DIMENSION_NAMES), goal


def test_goal_weights_alias_and_unknown():
    assert get_dimension_weights("条件谈判") == get_dimension_weights("条件收口")
    assert get_dimension_weights("再次推进") == get_dimension_weights("条件收口")
    assert get_dimension_weights("未知目标") == DIMENSION_WEIGHTS
    assert get_dimension_weights("") == DIMENSION_WEIGHTS


def test_all_five_scores_is_100():
    assert calculate_overall_score(_scores({n: 5 for n in DIMENSION_NAMES}), sales_turns=5) == 100
    assert calculate_overall_score(_scores({n: 5 for n in DIMENSION_NAMES}), sales_turns=5, goal="价格异议") == 100


def test_all_three_scores_is_60():
    assert calculate_overall_score(_scores({n: 3 for n in DIMENSION_NAMES}), sales_turns=5) == 60


def test_weighted_not_flat_average():
    # 默认权重下故障归因 0.10，单维 5 分时总分应低于权重 0.15 的维度
    only_fault = _scores({"故障归因": 5})
    only_craft = _scores({"工艺探询": 5})
    assert calculate_overall_score(only_fault, 5) < calculate_overall_score(only_craft, 5)


def test_price_goal_emphasizes_objection():
    # 价格异议：异议处理权重更高，同样单维 5 分应拉高更多
    only_objection = _scores({"异议处理": 5})
    base = calculate_overall_score(only_objection, 5)
    priced = calculate_overall_score(only_objection, 5, goal="价格异议")
    assert priced > base


def test_sales_turn_cap():
    full = _scores({n: 5 for n in DIMENSION_NAMES})
    assert calculate_overall_score(full, sales_turns=2) <= SALES_TURN_SCORE_CAP
    assert calculate_overall_score(full, sales_turns=3) == 100


def test_hard_cap_process_inquiry():
    scores = _scores({"工艺探询": 5, "推进动作": 5, "技术边界": 5})
    # 只提价格，未问水质/水温/工艺
    capped = enforce_hard_caps(scores, ["您这个报价有点高，能不能再优惠一点？"])
    by_name = {s["name"]: s for s in capped}
    assert by_name["工艺探询"]["value"] == HARD_CAP_VALUE
    assert by_name["推进动作"]["value"] == HARD_CAP_VALUE


def test_hard_cap_process_requires_two_categories():
    scores = _scores({"工艺探询": 5, "推进动作": 5, "技术边界": 5})
    # 只问了水质类（水硬度/硬水近义词不算两项），仍应封顶
    capped = enforce_hard_caps(scores, ["想确认一下您那边水硬度和硬水情况，下一步我们约工程师下周小样。"])
    by_name = {s["name"]: s for s in capped}
    assert by_name["工艺探询"]["value"] == HARD_CAP_VALUE
    assert by_name["推进动作"]["value"] == 5


def test_hard_cap_respects_process_ask_and_next_step():
    sales = [
        "想先确认一下您那边水质硬度和水温大概多少？工艺是浸轧还是浸渍？",
        "我们可以约工程师下周带小样上门，出日标测试报告。",
    ]
    scores = _scores({"工艺探询": 5, "推进动作": 5, "技术边界": 5})
    capped = enforce_hard_caps(scores, sales)
    by_name = {s["name"]: s for s in capped}
    assert by_name["工艺探询"]["value"] == 5
    assert by_name["推进动作"]["value"] == 5
    assert by_name["技术边界"]["value"] == 5


def test_hard_cap_overpromise_boundary():
    scores = _scores({"技术边界": 5, "工艺探询": 5, "推进动作": 5})
    sales = ["您放心，绝无问题，百分百不会出斑。水质水温我都问过了，浸轧工艺，下周约小样。"]
    capped = enforce_hard_caps(scores, sales)
    by_name = {s["name"]: s for s in capped}
    assert by_name["技术边界"]["value"] == HARD_CAP_VALUE
    assert by_name["工艺探询"]["value"] == 5
    assert by_name["推进动作"]["value"] == 5


def test_normalize_rejects_unknown_dimension():
    fallback = {"name": "工艺探询", "value": 3, "reason": "fallback"}
    item = {"name": "旧维度", "value": 5, "reason": "x"}
    normalized = normalize_score_item(item, fallback)
    assert normalized["name"] == "工艺探询"
    assert normalized["value"] == 5


def test_normalize_clamps_value():
    fallback = {"name": "工艺探询", "value": 3, "reason": "f"}
    assert normalize_score_item({"name": "工艺探询", "value": 99, "reason": "x"}, fallback)["value"] == 5
    assert normalize_score_item({"name": "工艺探询", "value": -1, "reason": "x"}, fallback)["value"] == 1


def test_formula_text_matches_weights():
    text = build_score_formula_text()
    for name, weight in DIMENSION_WEIGHTS.items():
        assert name in text
        assert str(weight) in text or f"{weight}" in text or f"{weight:.2f}" in text


def test_criteria_text_contains_weight_labels():
    text = build_scoring_criteria_text(2, 10.0, "价格异议", "商务谈判")
    assert "权重" in text
    assert "整体评分不得超过70分" in text
    assert "价格异议" in text
    # 价格异议调权后异议处理应为 25%
    assert "异议处理25%" in text or "权重25%" in text


def test_formula_text_uses_goal_weights():
    text = build_score_formula_text("价格异议")
    assert "异议处理×0.25" in text
