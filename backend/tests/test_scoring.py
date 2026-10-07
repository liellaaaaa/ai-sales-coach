"""scoring 模块单测：权重、封顶、维度白名单。"""
from app.services.scoring import (
    DIMENSION_NAMES,
    DIMENSION_WEIGHTS,
    SALES_TURN_SCORE_CAP,
    build_score_formula_text,
    build_scoring_criteria_text,
    calculate_overall_score,
    normalize_score_item,
)


def _scores(values: dict[str, int]) -> list[dict]:
    return [{"name": name, "value": values.get(name, 3), "reason": "x"} for name in DIMENSION_NAMES]


def test_weights_sum_to_one():
    assert abs(sum(DIMENSION_WEIGHTS.values()) - 1.0) < 1e-9


def test_all_five_scores_is_100():
    assert calculate_overall_score(_scores({n: 5 for n in DIMENSION_NAMES}), sales_turns=5) == 100


def test_all_three_scores_is_60():
    assert calculate_overall_score(_scores({n: 3 for n in DIMENSION_NAMES}), sales_turns=5) == 60


def test_weighted_not_flat_average():
    # 故障归因权重 0.10，单维 5 分时总分应低于权重 0.15 的维度
    only_fault = _scores({"故障归因": 5})
    only_craft = _scores({"工艺探询": 5})
    assert calculate_overall_score(only_fault, 5) < calculate_overall_score(only_craft, 5)


def test_sales_turn_cap():
    full = _scores({n: 5 for n in DIMENSION_NAMES})
    assert calculate_overall_score(full, sales_turns=2) <= SALES_TURN_SCORE_CAP
    assert calculate_overall_score(full, sales_turns=3) == 100


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
        assert str(weight) in text or f"{weight}" in text


def test_criteria_text_contains_weight_labels():
    text = build_scoring_criteria_text(2, 10.0, "价格异议", "商务谈判")
    assert "权重15%" in text
    assert "权重10%" in text
    assert "整体评分不得超过70分" in text
