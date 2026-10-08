"""plan_training（推进方案 → 针对性训练）提取与 prompt 注入测试。"""
from types import SimpleNamespace

from app.services.llm import LLMClient, _plan_training_active, _plan_training_context


def _session(setup_context: dict, training_type: str = "客户情景陪练") -> SimpleNamespace:
    return SimpleNamespace(
        training_type=training_type,
        stage="测试推进",
        goal="技术交涉",
        customer_name="测试客户",
        customer_type="印染厂",
        background="背景：夏季水温偏高，大货湿擦不稳。",
        setup_context=setup_context,
        messages=[],
        customer_difficulty="标准",
        customer_personality="谨慎型",
        customer_concern="品质",
    )


PLAN = {
    "source_session_id": 12,
    "plan_summary": "卡在测试口径",
    "primary_action": "约品牌端确认人对齐测试口径",
    "must_ask": "湿擦按日标还是国标测",
    "strategies": ["卡点复述", "条件换承诺"],
    "checklist": [{"title": "约测试确认人", "detail": "带上第三方报告", "due": "2 天内"}],
    "focus_scores": [{"name": "工艺探询", "value": 2, "reason": "未问清水温"}],
}


def test_extract_plan_training_full():
    ctx = _plan_training_context(_session({"plan_training": PLAN}))
    assert ctx["source_session_id"] == 12
    assert ctx["must_ask"] == "湿擦按日标还是国标测"
    assert ctx["primary_action"] == "约品牌端确认人对齐测试口径"
    assert ctx["strategies"] == ["卡点复述", "条件换承诺"]
    assert ctx["checklist"][0]["title"] == "约测试确认人"
    assert ctx["focus_scores"][0]["name"] == "工艺探询"
    assert _plan_training_active(ctx)


def test_extract_plan_training_tolerates_messy_fields():
    messy = {
        "plan_training": {
            "must_ask": "问水温",
            "strategies": "单字符串",
            "checklist": "不是列表",
            "focus_scores": [None, "工艺探询"],
            "source_session_id": "abc",
        }
    }
    ctx = _plan_training_context(_session(messy))
    assert ctx["must_ask"] == "问水温"
    assert ctx["strategies"] == ["单字符串"]
    assert ctx["checklist"] == []
    assert len(ctx["focus_scores"]) == 1 and ctx["focus_scores"][0]["name"] == "工艺探询"
    assert ctx["source_session_id"] is None


def test_extract_plan_training_missing_returns_empty():
    ctx = _plan_training_context(_session({}))
    assert not _plan_training_active(ctx)
    assert ctx["must_ask"] == "" and ctx["strategies"] == []


def test_customer_prompt_includes_focus_block_only_with_plan():
    llm = LLMClient()
    with_plan = llm._customer_prompt(_session({"plan_training": PLAN}), [])
    assert "训练焦点" in with_plan
    assert "湿擦按日标还是国标测" in with_plan
    assert "约品牌端确认人对齐测试口径" in with_plan

    without = llm._customer_prompt(_session({}), [])
    assert "训练焦点" not in without
    assert "湿擦按日标还是国标测" not in without


def test_report_prompt_marks_targeted_training_only_with_plan():
    llm = LLMClient()
    with_plan = llm._report_prompt(_session({"plan_training": PLAN}), [], [])
    assert "针对性训练" in with_plan
    assert "湿擦按日标还是国标测" in with_plan
    assert "约品牌端确认人对齐测试口径" in with_plan

    without = llm._report_prompt(_session({}), [], [])
    assert "针对性训练" not in without
    assert "湿擦按日标还是国标测" not in without


def test_mock_customer_reply_uses_plan_focus():
    llm = LLMClient()
    reply = llm._mock_customer_reply(_session({"plan_training": PLAN}), [])
    assert "湿擦按日标还是国标测" in reply or "约品牌端确认人对齐测试口径" in reply


def test_mock_report_uses_plan_focus_not_generic():
    llm = LLMClient()
    report = llm._mock_report(_session({"plan_training": PLAN}), [], [])
    blob = str(report)
    assert "湿擦按日标还是国标测" in blob or "约品牌端确认人对齐测试口径" in blob
    assert "保持沟通" not in report["summary"]


def test_fallback_suggested_reply_uses_plan_focus():
    llm = LLMClient()
    fallback = llm._fallback_suggested_reply(_session({"plan_training": PLAN}), [])
    assert "湿擦按日标还是国标测" in fallback["content"] or "约品牌端确认人对齐测试口径" in fallback["content"]


def test_opportunity_mock_untouched_by_plan():
    llm = LLMClient()
    opp = _session({"plan_training": PLAN, "opportunity_setup": {"decision_blocker": "测试标准未对齐"}}, training_type="商机推进教练")
    report = llm._mock_report(opp, [], [])
    assert "关键阻碍" in report["summary"] or "测试标准未对齐" in report["summary"]
