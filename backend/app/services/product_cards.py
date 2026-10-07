from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

# 产品卡内容提炼自 kb/ 研发培训资料，字段固定：
# code / title / positioning / process / params / boundaries / faults / certs / cases
# 数据外置到 config/product_cards.json，改卡不必改代码（改完需重启服务）。

_CARDS_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "product_cards.json"


def _load_cards_config() -> tuple[list[dict], dict[str, set[str]]]:
    data = json.loads(_CARDS_CONFIG_PATH.read_text(encoding="utf-8"))
    cards = data.get("cards") or []
    hints_raw = data.get("match_hints") or {}
    hints = {key: set(values) for key, values in hints_raw.items()}
    return cards, hints


PRODUCT_CARDS, _CARD_MATCH_HINTS = _load_cards_config()


_MODEL_PATTERN = re.compile(
    r"(HT-\d{3,5}[A-Z]?|HT-?\d{3,5}|831B|8667|833|868|7891|H7-5|HT-766|HT-790|HT-5095)",
    re.IGNORECASE,
)

_LIST_FIELDS = ("process", "params", "boundaries", "faults", "certs", "cases")
_STR_FIELDS = ("code", "title", "positioning")


def _as_lines(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (list, tuple, set)):
        lines: list[str] = []
        for item in value:
            text = str(item).strip()
            if text:
                lines.append(text)
        return lines
    text = str(value).strip()
    return [text] if text else []


def _session_attr(session: Any, name: str, default: str = "") -> str:
    if session is None:
        return default
    if isinstance(session, Mapping):
        value = session.get(name, default)
        return str(value).strip() if value is not None else default
    value = getattr(session, name, default)
    if value is None:
        return default
    return str(value).strip()


def _session_blob(session: Any, knowledge: Iterable[Any] | None = None) -> str:
    parts = [
        _session_attr(session, "stage"),
        _session_attr(session, "goal"),
        _session_attr(session, "background"),
        _session_attr(session, "customer_type"),
        _session_attr(session, "training_type"),
        _session_attr(session, "product_name"),
        _session_attr(session, "product"),
        _session_attr(session, "product_code"),
    ]
    setup = _session_attr(session, "setup_context", "")
    if setup and setup not in {"{}", "None"}:
        parts.append(setup)
    if knowledge:
        for item in knowledge:
            if item is None:
                continue
            if isinstance(item, Mapping):
                for key in ("title", "content", "section_title", "chunk_type", "source_name"):
                    value = item.get(key)
                    if value:
                        parts.append(str(value))
            else:
                for key in ("title", "content", "section_title", "chunk_type", "source_name"):
                    value = getattr(item, key, None)
                    if value:
                        parts.append(str(value))
    return "\n".join(part for part in parts if part)


def _card_blob(card: Mapping[str, Any]) -> str:
    parts = [str(card.get("code") or ""), str(card.get("title") or ""), str(card.get("positioning") or "")]
    for field in _LIST_FIELDS:
        parts.extend(_as_lines(card.get(field)))
    return "\n".join(parts)


def _score_card(card: Mapping[str, Any], session_text: str, product_field: str) -> int:
    code = str(card.get("code") or "")
    title = str(card.get("title") or "")
    text_l = session_text.lower()
    product_l = product_field.lower()
    score = 0

    if code and product_field:
        code_l = code.lower()
        if code_l == product_l or code_l in product_l or product_l in code_l:
            score += 30
        else:
            digits = re.sub(r"[^0-9a-z]", "", code_l)
            if digits and len(digits) >= 3 and digits in re.sub(r"[^0-9a-z]", "", product_l):
                score += 24

    if code and code.lower() in text_l:
        score += 12
    for token in re.findall(r"[A-Za-z0-9_+-]{2,}", title):
        if len(token) >= 2 and token.lower() in text_l:
            score += 3

    hints = _CARD_MATCH_HINTS.get(code, set())
    for hint in hints:
        if hint.lower() in text_l:
            score += 3

    # 决策辅助卡在故障/选型类场景加权
    if code in {"fault-wet-rub", "guide-wen-wen"}:
        if any(k in session_text for k in ("出斑", "湿擦斑", "破乳", "斑", "选型", "怎么选", "推荐", "方案", "故障")):
            score += 6

    # 产品卡在技术类目标下加权
    if code not in {"fault-wet-rub", "guide-wen-wen"}:
        if any(k in session_text for k in ("技术交涉", "方案论证", "试样", "参数", "工艺", "牢度", "固色", "湿擦")):
            score += 2

    return score


def get_relevant_cards(session: Any, knowledge: Any = None, limit: int = 3) -> list[dict]:
    """根据训练 session（stage/goal/background/product 字段）返回相关产品卡。

    session 可能是 TrainingSession 也可能是带属性的 dict 包装对象。
    knowledge 可选：已检索到的知识条目，用于补充匹配线索。
    返回 list[dict]，字段固定为 code/title/positioning/process/params/boundaries/faults/certs/cases。
    """
    if limit <= 0:
        return []
    knowledge_list: list[Any]
    if knowledge is None:
        knowledge_list = []
    elif isinstance(knowledge, (list, tuple, set)):
        knowledge_list = list(knowledge)
    else:
        knowledge_list = [knowledge]

    session_text = _session_blob(session, knowledge_list)
    product_field = " ".join(
        filter(
            None,
            [
                _session_attr(session, "product_name"),
                _session_attr(session, "product"),
                _session_attr(session, "product_code"),
            ],
        )
    )

    scored = [(_score_card(card, session_text, product_field), index, card) for index, card in enumerate(PRODUCT_CARDS)]
    scored.sort(key=lambda item: (-item[0], item[1]))
    if scored and scored[0][0] > 0:
        return [card for _, _, card in scored[:limit]]

    # 无命中时给出默认组合：一张核心产品卡 + 决策辅助卡
    defaults = ["HT-766", "833", "guide-wen-wen"]
    by_code = {str(card.get("code")): card for card in PRODUCT_CARDS}
    fallback = [by_code[code] for code in defaults if code in by_code]
    if len(fallback) < limit:
        for card in PRODUCT_CARDS:
            if card not in fallback:
                fallback.append(card)
            if len(fallback) >= limit:
                break
    return fallback[:limit]


def cards_to_prompt_text(cards: list[dict]) -> str:
    """把产品卡转成紧凑中文文本，注入 LLM prompt。

    每卡含型号、定位、适用条件、参数、技术边界、常见故障、认证、案例。
    """
    if not cards:
        return ""
    blocks: list[str] = []
    for card in cards:
        if not isinstance(card, Mapping):
            continue
        code = str(card.get("code") or "").strip()
        title = str(card.get("title") or "").strip()
        head = f"【{code}】{title}" if code else f"【产品】{title}"
        lines = [head]
        positioning = _as_lines(card.get("positioning"))
        if positioning:
            lines.append("定位：" + "；".join(positioning))
        process = _as_lines(card.get("process"))
        if process:
            lines.append("适用条件/工艺：" + "；".join(process))
        params = _as_lines(card.get("params"))
        if params:
            lines.append("参数：" + "；".join(params))
        boundaries = _as_lines(card.get("boundaries"))
        if boundaries:
            lines.append("技术边界：" + "；".join(boundaries))
        faults = _as_lines(card.get("faults"))
        if faults:
            lines.append("常见故障：" + "；".join(faults))
        certs = _as_lines(card.get("certs"))
        if certs:
            lines.append("认证/合规：" + "；".join(certs))
        cases = _as_lines(card.get("cases"))
        if cases:
            lines.append("案例：" + "；".join(cases))
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
