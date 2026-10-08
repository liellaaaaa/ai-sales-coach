import json
import logging
import re
import time
from typing import Any, AsyncGenerator

import httpx

from app.models import KnowledgeItem, TrainingMessage, TrainingSession
from app.services.llm_config import EffectiveLLMConfig, get_effective_llm_config
from app.services.llm_providers import (
    _anthropic_messages,
    _openai_messages,
    _post_json,
    _strip_thinking,
    resolve_provider,
)
from app.services.scoring import (
    MIN_SALES_TURNS_FOR_FULL_SCORE,
    build_score_formula_text,
    build_scoring_criteria_text,
    calculate_overall_score,
    enforce_hard_caps,
    normalize_score_item,
)

logger = logging.getLogger(__name__)

__all__ = ["LLMClient", "extract_speaker", "SPEAKER_PATTERN", "_strip_thinking"]

# ---------------------------------------------------------------------------
# 角色标签解析：客户回复开头 [buyer] [tech] [boss] 或 [采购] [技术] [老板/厂长]
# ---------------------------------------------------------------------------
_SPEAKER_ALIASES = {
    "buyer": "buyer",
    "customer": "buyer",
    "采购": "buyer",
    "客户": "buyer",
    "tech": "tech",
    "技术": "tech",
    "技术主管": "tech",
    "boss": "boss",
    "老板": "boss",
    "厂长": "boss",
}

# 技术主管 必须排在 技术 之前，保证长标签优先
_SPEAKER_TOKEN = "buyer|tech|boss|采购|技术主管|技术|老板|厂长"

# 括号形式：[buyer] （tech） [技术主管] [厂长] 等（开括号必给，闭括号可省）
_SPEAKER_BRACKET_RE = re.compile(
    rf"^[\[（(]\s*({_SPEAKER_TOKEN})\s*[\]）)]?\s*[:：]?\s*",
    re.IGNORECASE,
)
# 裸英文标签：buyer/tech/boss 开头且后不接拉丁字母
_SPEAKER_BARE_EN_RE = re.compile(
    r"^(buyer|tech|boss)(?![A-Za-z])[:：]?\s*",
    re.IGNORECASE,
)
# 裸中文标签：必须跟冒号（技术：/采购：），不用空白作分隔，避免误伤「技术 这块…」「采购 这边…」
_SPEAKER_BARE_ZH_RE = re.compile(
    rf"^({_SPEAKER_TOKEN})\s*[:：]\s*",
)

# 供路由等复用的宽松识别（含可选括号）
SPEAKER_PATTERN = re.compile(
    rf"^[\[（(]?\s*({_SPEAKER_TOKEN})[\]）)]?\s*[:：]?\s*",
    re.IGNORECASE,
)


def extract_speaker(text: str) -> tuple[str, str]:
    """返回 (speaker, clean_text)。speaker ∈ buyer|tech|boss，无标签默认 buyer。"""
    raw = (text or "").strip()
    for pattern in (_SPEAKER_BRACKET_RE, _SPEAKER_BARE_EN_RE, _SPEAKER_BARE_ZH_RE):
        match = pattern.match(raw)
        if not match:
            continue
        speaker = _SPEAKER_ALIASES.get(match.group(1).lower())
        if speaker:
            return speaker, raw[match.end() :].strip()
        break
    return "buyer", raw


class _DictObj:
    """将 dict 包装为支持属性访问的对象，用于 SSE 快照。"""

    def __init__(self, d: dict):
        self._d = d

    def __getattr__(self, name: str):
        try:
            return self._d[name]
        except KeyError:
            raise AttributeError(name)


def _excerpt(text: str, limit: int = 1200) -> str:
    return " ".join((text or "").split())[:limit]


def _knowledge_text(items: list[KnowledgeItem]) -> str:
    """知识库注入文本：recommended/banned 保留全文，仅截断 content。"""
    lines = []
    for item in items:
        location = item.section_title or "未标注章节"
        if item.page_start and item.page_end and item.page_end != item.page_start:
            location = f"{location} / 第 {item.page_start}-{item.page_end} 页"
        elif item.page_start:
            location = f"{location} / 第 {item.page_start} 页"
        recommended = " ".join((item.recommended or "").split())
        banned = " ".join((item.banned or "").split())
        lines.append(
            "- "
            f"source:{item.source_name}; doc_type:{item.source_type}; chunk_type:{item.chunk_type}; "
            f"section:{location}; confidence:{item.confidence}; stage:{item.stage}; scenario:{item.scenario}; "
            f"recommended:{recommended}; banned:{banned}; content:{_excerpt(item.content)}"
        )
    return "\n".join(lines)


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, bool):
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    return str(value).strip()


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (list, tuple)):
        items: list[str] = []
        for item in value:
            if isinstance(item, dict):
                text = _as_str(item.get("text") or item.get("title") or item.get("name") or item.get("content"))
            else:
                text = _as_str(item)
            if text:
                items.append(text)
        return items
    text = _as_str(value)
    return [text] if text else []


def _plan_checklist_items(value: Any) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    raw = value if isinstance(value, (list, tuple)) else []
    for item in raw:
        if isinstance(item, dict):
            title = _as_str(item.get("title") or item.get("name"))
            detail = _as_str(item.get("detail") or item.get("content") or item.get("task"))
            due = _as_str(item.get("due") or item.get("deadline") or item.get("time"))
            if title or detail:
                items.append({"title": title, "detail": detail, "due": due})
        else:
            text = _as_str(item)
            if text:
                items.append({"title": text, "detail": "", "due": ""})
    return items


def _plan_focus_score_items(value: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    raw = value if isinstance(value, (list, tuple)) else []
    for item in raw:
        if isinstance(item, dict):
            name = _as_str(item.get("name"))
            if not name:
                continue
            raw_value = item.get("value", "")
            if isinstance(raw_value, bool):
                score_value: Any = ""
            elif isinstance(raw_value, (int, float)):
                score_value = int(raw_value)
            elif isinstance(raw_value, str):
                score_value = raw_value.strip()
            else:
                score_value = _as_str(raw_value)
            items.append({"name": name, "value": score_value, "reason": _as_str(item.get("reason"))})
        else:
            text = _as_str(item)
            if text:
                items.append({"name": text, "value": "", "reason": ""})
    return items


def _plan_training_context(session: Any) -> dict:
    """从 setup_context.plan_training 读取推进方案训练焦点，列表/字符串/缺省均容错。"""
    empty = {
        "source_session_id": None,
        "plan_summary": "",
        "primary_action": "",
        "must_ask": "",
        "strategies": [],
        "checklist": [],
        "focus_scores": [],
    }
    if isinstance(session, dict):
        setup = session.get("setup_context")
    else:
        setup = getattr(session, "setup_context", None)
    if not isinstance(setup, dict):
        return dict(empty)
    plan = setup.get("plan_training")
    if not isinstance(plan, dict):
        return dict(empty)

    source_id = plan.get("source_session_id")
    if isinstance(source_id, bool):
        source_id = None
    elif isinstance(source_id, int):
        pass
    else:
        try:
            source_id = int(source_id) if source_id is not None and source_id != "" else None
        except (TypeError, ValueError):
            source_id = None

    return {
        "source_session_id": source_id,
        "plan_summary": _as_str(plan.get("plan_summary")),
        "primary_action": _as_str(plan.get("primary_action")),
        "must_ask": _as_str(plan.get("must_ask")),
        "strategies": _as_str_list(plan.get("strategies")),
        "checklist": _plan_checklist_items(plan.get("checklist")),
        "focus_scores": _plan_focus_score_items(plan.get("focus_scores")),
    }


def _plan_training_active(plan: dict) -> bool:
    return bool(
        (plan or {}).get("plan_summary")
        or (plan or {}).get("primary_action")
        or (plan or {}).get("must_ask")
        or (plan or {}).get("strategies")
        or (plan or {}).get("checklist")
        or (plan or {}).get("focus_scores")
    )


def _plan_focus_lines(plan: dict) -> list[str]:
    """把 plan_training 格式化成「优先推进动作 / 必须问清 / …」要点行。"""
    lines: list[str] = []
    if plan.get("primary_action"):
        lines.append(f"优先推进动作：{plan['primary_action']}")
    if plan.get("must_ask"):
        lines.append(f"必须问清：{plan['must_ask']}")
    strategies = plan.get("strategies") or []
    if strategies:
        lines.append(f"交涉策略：{'；'.join(strategies)}")
    checklist = plan.get("checklist") or []
    if checklist:
        parts = []
        for item in checklist:
            title = (item.get("title") or "").strip()
            detail = (item.get("detail") or "").strip()
            due = (item.get("due") or "").strip()
            text = title
            if detail:
                text = f"{text}（{detail}）" if text else detail
            if due:
                text = f"{text}｜{due}" if text else due
            if text:
                parts.append(text)
        if parts:
            lines.append(f"执行清单：{'；'.join(parts)}")
    focus_scores = plan.get("focus_scores") or []
    if focus_scores:
        parts = []
        for item in focus_scores:
            name = (item.get("name") or "").strip()
            value = item.get("value", "")
            reason = (item.get("reason") or "").strip()
            text = name
            if value != "" and value is not None:
                text = f"{text}（{value}）" if text else str(value)
            if reason:
                text = f"{text}：{reason}" if text else reason
            if text:
                parts.append(text)
        if parts:
            lines.append(f"薄弱维度：{'；'.join(parts)}")
    return lines


def _plan_customer_block(plan: dict) -> str:
    if not _plan_training_active(plan):
        return ""
    lines = ["# 本次针对推进方案的训练焦点", "本轮是针对推进方案的针对性训练，客户出题必须围绕以下焦点施压："]
    for focus_line in _plan_focus_lines(plan):
        lines.append(f"- {focus_line}")
    lines.append(
        "出题契约补充：客户要围绕这些焦点施压——尤其是「必须问清」的点，"
        "业务员若不问到位就不要轻易放行下一步；对薄弱维度对应的话题继续追问。"
        "语气仍是客户，不要替业务员说话。"
    )
    return "\n".join(lines) + "\n\n"


def _customer_profile_text(session: TrainingSession) -> str:
    difficulty = getattr(session, "customer_difficulty", "") or "标准"
    personality = getattr(session, "customer_personality", "") or "谨慎型"
    concern = getattr(session, "customer_concern", "") or "供应稳定"
    relationship = getattr(session, "customer_type", "") or ""
    setup = getattr(session, "setup_context", None) or {}
    persona = ""
    if isinstance(setup, dict):
        persona = (
            (setup.get("customer_info") or {}).get("customer_persona")
            or (setup.get("training_profile") or {}).get("customer_persona")
            or ""
        )
    parts = [f"客户关系：{relationship}" if relationship else "", f"客户画像：{persona}" if persona else ""]
    parts.extend([f"客户难度：{difficulty}", f"客户性格：{personality}", f"核心关注：{concern}"])
    return "；".join(p for p in parts if p)


def _product_cards_text(session: Any, knowledge: list[KnowledgeItem] | None = None) -> str:
    """产品卡文本；product_cards 缺失或调用失败时降级为空串，不影响主流程。"""
    try:
        from app.services.product_cards import cards_to_prompt_text, get_relevant_cards
    except Exception:
        return ""
    try:
        cards = get_relevant_cards(session, knowledge=knowledge, limit=3)
    except Exception as exc:
        logger.debug("get_relevant_cards failed: %s", exc)
        return ""
    try:
        return cards_to_prompt_text(cards) or ""
    except Exception as exc:
        logger.debug("cards_to_prompt_text failed: %s", exc)
        return ""


class LLMClient:
    def _customer_prompt(self, session: TrainingSession, knowledge: list[KnowledgeItem]) -> str:
        """客户出题契约 prompt，customer_reply 与 customer_reply_stream 共用。"""
        cards_text = _product_cards_text(session, knowledge)
        cards_block = f"\n{cards_text}" if cards_text else ""
        plan_block = _plan_customer_block(_plan_training_context(session))
        return (
            "# 角色\n"
            "你是真实客户，不是业务员。你是广东珠三角印染厂的采购/技术/厂长，正在和一家纺织助剂供应商的业务员对话。\n"
            "你只能以客户身份说话，绝对不要替业务员回答、不要帮业务员出主意、不要说业务员会说的话。\n"
            "不要轻易被说服，要围绕客户背景、商机阶段和训练目标持续追问、施压、提条件。\n"
            "每次回复控制在 80 字以内，像真实客户自然说话。不要输出编号、不要分点、不要解释。\n\n"
            "# 多角色出题（本轮谁说话）\n"
            "当前说话人可能是三人之一，同一轮只有一个人说话：\n"
            "- [buyer] 采购：压价、账期、交期、对比竞品、要条件。\n"
            "- [tech] 技术主管：工艺/参数/测试标准/同浴/水质/大小样，专业挑剔。\n"
            "- [boss] 厂长/老板：拍板、底线、总成本、停线风险，话少但重。\n"
            "AI 自行决定本轮谁说话：默认 buyer；当涉及技术细节/工艺边界/测试方法时切 tech；"
            "当涉及价格底线/是否合作/停线索赔/最终拍板时切 boss。\n"
            "回复格式（必须遵守）：必须以角色标签开头，例如 [tech]你们湿擦跟固色剂能不能同浴？ 或 [boss]你先给个诚意价。\n"
            "可以在台词里自然带入场感，如 [tech]我插一句…、[boss]这个我定一下…。\n\n"
            "# 出题契约（必须遵守）\n"
            "1. 必须从下方产品与工艺资料中的产品型号、参数、工艺条件、技术边界、常见故障里，挑 1–2 个具体点追问或质疑，不要空泛聊天。\n"
            "   追问优先来自知识/产品卡中的技术边界、常见故障、认证与测试标准："
            "技术边界（涂料/化纤难提升、大货小样差异、同浴沉淀、适用 pH/温度窗口）、"
            "常见故障（色变、沾色、破乳、湿擦掉级、气味）、"
            "认证与测试标准（bluesign/GOTS/OEKO-TEX/ZDHC，日标/国标/湿摩擦级数怎么测）。\n"
            "2. 追问风格参考（口语、具体，照着这种味道说）：\n"
            "   - [tech]你们湿擦跟固色剂能不能同浴？\n"
            "   - [buyer]我们水硬度高、夏天水温五六十度，用哪一款？\n"
            "   - [buyer]大货会不会比小样差半级？\n"
            "   - [tech]日标还是国标测的？标准都不一样\n"
            "   - [tech]涂料/化纤是不是根本提不上来？\n"
            "   - [tech]HT-790 真不含双酚？残留多少？\n"
            "   - [tech]你们过的是 OEKO-TEX 还是 ZDHC？报告拿来看\n"
            "   - [boss]你先给个诚意价。\n"
            "3. 业务员若不问清水质、水温、使用工艺（浸轧/浸渍/喷淋）、布种、测试标准，就不要给完整信息：可以不耐烦、反问、或只给部分条件。\n"
            "4. 不要编造资料里没有的产品事实；资料里没有的信息就说「不清楚/要问技术」。\n"
            "5. 可以压价、施压，但必须挂在具体产品/工艺点上（某型号效果、某工艺风险、某测试标准），不要空泛说「太贵了」。"
            "涉及价格/账期/交期时，可结合资料里 recommended/banned 的商务口径施压："
            "拿推荐口径里的价值点反向压条件（既然省水省时/认证过硬，价格就该更优），"
            "或用禁用口径里的风险点施压（大货不稳、返修、停线谁担），不要站到业务员立场替对方圆场。\n"
            "6. 不要向业务员背诵资料原文，不要报来源、不要念参数表。\n"
            "7. 你是客户，不是业务员：不要替对方总结卖点、不要主动帮业务员推进成交、不要给出可直接照念的成单话术。\n\n"
            "# 客户画像\n"
            f"{_customer_profile_text(session)}\n"
            "注意：客户关系只表示是否有合作，不代表价格态度；陌拜新客户也可能专业、关注品质或工艺，不一定是价格敏感。\n"
            f"客户公司：{session.customer_name} / {session.customer_type}\n"
            f"训练类型：{session.training_type}\n商机阶段：{session.stage}\n训练目标：{session.goal}\n"
            f"背景：{session.background}\n\n"
            f"{plan_block}"
            "# 产品与工艺资料（出题依据：必须从中挑具体点追问；不要向业务员背诵原文）\n"
            f"{_knowledge_text(knowledge)}"
            f"{cards_block}"
        )

    async def customer_reply(
        self,
        session: TrainingSession,
        messages: list[TrainingMessage],
        knowledge: list[KnowledgeItem],
    ) -> str:
        config = get_effective_llm_config()
        if not self._configured(config):
            return self._mock_customer_reply(session, messages)

        prompt = self._customer_prompt(session, knowledge)
        history = [{"sender_type": "BOT", "text": prompt}]
        for msg in messages[-8:]:
            sender = "USER" if msg.role == "sales" else "BOT"
            history.append({"sender_type": sender, "text": msg.content})
        try:
            data = await self._chat(history, config, max_tokens=1024)
        except httpx.HTTPError:
            data = ""
        return data or self._mock_customer_reply(session, messages)

    async def customer_reply_stream(
        self,
        session,
        messages,
        knowledge,
    ) -> AsyncGenerator[str, None]:
        """流式生成客户回复，逐 chunk yield 文本片段。支持 session 为 dict 或 TrainingSession。"""
        if isinstance(session, dict):
            session = _DictObj(session)

        config = get_effective_llm_config()
        if not self._configured(config):
            yield self._mock_customer_reply(session, messages)
            return

        prompt = self._customer_prompt(session, knowledge)
        history = [{"sender_type": "BOT", "text": prompt}]
        for msg in messages[-8:]:
            role = msg.get("role") if isinstance(msg, dict) else msg.role
            content = msg.get("content") if isinstance(msg, dict) else msg.content
            sender = "USER" if role == "sales" else "BOT"
            history.append({"sender_type": sender, "text": content})
        try:
            async for chunk in self._chat_stream(history, config, max_tokens=1024):
                yield chunk
        except httpx.HTTPError:
            yield self._mock_customer_reply(session, messages)

    async def score_report(
        self,
        session: TrainingSession,
        messages: list[TrainingMessage],
        knowledge: list[KnowledgeItem],
    ) -> dict:
        config = get_effective_llm_config()
        is_opportunity = self._is_opportunity(session)
        if not self._configured(config):
            report = self._mock_report(session, messages, knowledge)
            report["llm_status"] = "mock:not_configured"
            return self._normalize_report(report, session, knowledge)

        prompt = self._report_prompt(session, messages, knowledge)
        try:
            data = await self._chat([{"sender_type": "USER", "text": prompt}], config, max_tokens=4096)
            llm_status = "llm"
        except httpx.HTTPError as exc:
            data = ""
            llm_status = f"mock:http_error:{exc.__class__.__name__}"
        parsed = self._parse_json_object(data)
        if parsed is None and data.strip():
            repaired = await self._repair_json(data, config)
            parsed = self._parse_json_object(repaired)
            if parsed is not None:
                llm_status = "llm:repaired"
        if parsed is None:
            parsed = self._mock_report(session, messages, knowledge)
            parsed["llm_status"] = f"mock:invalid_json:{llm_status}"
        else:
            parsed["llm_status"] = llm_status
        normalized = self._normalize_report(parsed, session, knowledge)
        # 内部状态不进引用依据，只挂在独立字段供日志/调试
        normalized["llm_status"] = parsed.get("llm_status", llm_status)
        return normalized

    async def suggested_reply(
        self,
        session: TrainingSession,
        messages: list[TrainingMessage],
        knowledge: list[KnowledgeItem],
    ) -> dict[str, str]:
        """返回 {"content": 可直接说的口语回复, "source": 可选依据}。知识库优先。"""
        last_customer = next((msg.content for msg in reversed(messages) if msg.role == "customer"), "")
        config = get_effective_llm_config()
        if not self._configured(config):
            return self._fallback_suggested_reply(session, knowledge)
        transcript = "\n".join(f"{m.role}: {m.content}" for m in messages[-8:])
        cards_text = _product_cards_text(session, knowledge)
        cards_block = f"\n产品卡（型号与边界必须对齐）：\n{cards_text}" if cards_text else ""
        plan = _plan_training_context(session)
        plan_block = ""
        if _plan_training_active(plan):
            focus_lines = _plan_focus_lines(plan)
            plan_block = (
                "# 本次针对推进方案的训练焦点（有知识库仍知识库优先，但话术要覆盖这些焦点）\n"
                + "\n".join(f"- {line}" for line in focus_lines)
                + "\n优先围绕「必须问清」和「优先推进动作」给出可开口的推进话术。\n"
            )
        prompt = (
            "# 角色\n"
            "你是纺织助剂销售话术教练。请给业务员一条可直接说出口的下一句回复。\n\n"
            "# 知识库优先话术契约（必须遵守）\n"
            "1. 必须优先改写下方知识条目里的 recommended 推荐话术，把它变成对客户说的自然口语；"
            "绝对禁止使用 banned 禁用话术，也不要输出与其冲突的说法。\n"
            "2. 必须回应客户最后一句的具体点（型号 / 工艺 / 价格 / 交期 / 测试标准等），不要答非所问。\n"
            "3. 若有产品卡：提到的型号、参数、技术边界必须与产品卡和知识库对齐，不得编造资料外型号或数据。\n"
            "4. 禁止空泛话术：不要说「保持沟通」「没问题」「尽量满足您」这类不落地的话，必须落到具体条件或下一步动作。\n"
            "5. 不要承诺无法确认的数据，不要直接降价。\n\n"
            "# 输出格式（必须遵守）\n"
            "第 1 行：1 句可直接说出口的口语回复，不超过 80 字，不要引号、不要编号、不要解释。\n"
            "第 2 行（可选）：依据：<一句话说明改写自哪条知识/产品点，不超过 30 字>\n"
            "不要输出其它内容。\n\n"
            f"客户最后一句：{last_customer}\n"
            f"训练类型：{session.training_type}\n阶段：{session.stage}\n目标：{session.goal}\n"
            f"客户：{session.customer_name} / {session.customer_type}\n背景：{session.background}\n"
            f"{plan_block}"
            f"知识库：\n{_knowledge_text(knowledge)}\n"
            f"{cards_block}\n"
            f"最近对话：\n{transcript}"
        )
        try:
            data = await self._chat([{"sender_type": "USER", "text": prompt}], config, max_tokens=1024)
        except httpx.HTTPError:
            return self._fallback_suggested_reply(session, knowledge)
        parsed = self._parse_suggested_reply(data)
        if not parsed.get("content"):
            return self._fallback_suggested_reply(session, knowledge)
        return parsed

    def _parse_suggested_reply(self, text: str) -> dict[str, str]:
        raw = _strip_thinking(text or "").strip()
        if raw.startswith("```"):
            raw = raw.removeprefix("```json").removeprefix("```").strip()
            raw = raw.removesuffix("```").strip()
        raw = raw.strip().strip('"“”')
        content = ""
        source = ""
        for line in raw.splitlines():
            cleaned = line.strip().strip('"“”')
            if not cleaned:
                continue
            if re.match(r"^(依据|理由|出处|参考)\s*[：:]", cleaned):
                source = re.sub(r"^(依据|理由|出处|参考)\s*[：:]\s*", "依据：", cleaned)
                continue
            if not content:
                content = cleaned
        if content and not source:
            match = re.search(r"[（(]\s*(依据|理由)\s*[：:]\s*([^）)]+)[）)]\s*$", content)
            if match:
                source = f"依据：{match.group(2).strip()}"
                content = content[: match.start()].strip()
        return {"content": content.strip(), "source": source.strip()}

    def _fallback_suggested_reply(
        self,
        session: TrainingSession,
        knowledge: list[KnowledgeItem] | None,
    ) -> dict[str, str]:
        """LLM 不可用时：优先用知识条目 recommended 拼 1-2 句可说回复，不再给通用套话。"""
        speakable: list[str] = []
        source = ""
        plan = _plan_training_context(session)
        plan_active = _plan_training_active(plan)
        for item in knowledge or []:
            rec = (getattr(item, "recommended", "") or "").strip()
            if not rec:
                continue
            line = self._recommended_to_speech(rec)
            if line and line not in speakable:
                speakable.append(line)
            if not source:
                name = getattr(item, "source_name", "") or getattr(item, "title", "") or "知识库"
                source = f"依据：改写自《{name}》推荐话术"
            if len(speakable) >= 2:
                break
        if speakable:
            content = speakable[0]
            if len(speakable) > 1:
                content = f"{speakable[0]}另外，{speakable[1]}"
            goal = getattr(session, "goal", "") or ""
            if goal and source:
                source = f"{source}；目标：{goal}"
            return {"content": content, "source": source}
        if plan_active:
            must_ask = plan.get("must_ask") or ""
            primary_action = plan.get("primary_action") or ""
            goal = getattr(session, "goal", "") or ""
            if must_ask and primary_action:
                content = f"您刚才提到的点我记下了。关于{must_ask}，我先把条件问清对齐，再按「{primary_action}」把下一步定下来。"
                source = f"依据：围绕推进方案「必须问清」与「优先推进动作」的推进话术"
            elif must_ask:
                content = f"关于{must_ask}，我先把关键条件问清对齐，确认完我们再约时间定下一步。"
                source = "依据：围绕推进方案「必须问清」的推进话术"
            elif primary_action:
                content = f"下一步我建议按「{primary_action}」推进，先把责任人、时间和条件定清，您看这样安排行吗？"
                source = "依据：围绕推进方案「优先推进动作」的推进话术"
            else:
                content = "您刚提到的这点我记下了，我先把推进方案里的关键条件和边界跟您对齐，再约时间把下一步定下来。"
                source = "依据：围绕推进方案焦点的推进动作"
            if goal:
                source = f"{source}；目标：{goal}" if source else f"依据：目标：{goal}"
            return {"content": content, "source": source}
        goal = getattr(session, "goal", "") or ""
        return {
            "content": "您刚提到的这点我记下了，我先把关键条件和边界跟您对齐，再约时间把下一步定下来。",
            "source": f"依据：围绕训练目标「{goal}」的通用推进动作" if goal else "",
        }

    def _recommended_to_speech(self, rec: str) -> str:
        """把教练指令式 recommended 改写成对客可说的口语短句。"""
        t = " ".join((rec or "").split()).strip().rstrip("。；;.!！")
        if not t:
            return ""
        t = t.replace("客户", "您")
        t = re.sub(r"^先", "我先", t)
        t = re.sub(r"，再", "，然后我再", t, count=1)
        t = re.sub(r"^再", "然后我再", t)
        t = re.sub(r"^把", "我把", t)
        t = re.sub(r"^用", "我用", t)
        if not re.match(r"^(我|您|咱们|我们)", t):
            t = f"我建议咱们{t}"
        return f"{t}。"

    async def live_tip(self, session, messages, knowledge, context: str = "after_sales") -> list[str]:
        """返回 1-2 条短提示。基于最新对话，提醒工艺探询/选型风险/推进动作/禁用话术。"""
        fallback = self._fallback_live_tips(knowledge)
        config = get_effective_llm_config()
        if not self._configured(config):
            return fallback
        prompt = self._live_tip_prompt(session, messages, knowledge, context=context)
        try:
            data = await self._chat([{"sender_type": "USER", "text": prompt}], config, max_tokens=200)
        except Exception as exc:
            logger.warning("live_tip 调用失败：%s", exc)
            return fallback
        tips = self._parse_live_tips(data)
        return tips or fallback

    def _fallback_live_tips(self, knowledge: list[KnowledgeItem] | None = None) -> list[str]:
        """无 LLM 时优先从知识条目 recommended/banned 提炼短提示。"""
        tips: list[str] = []
        for item in knowledge or []:
            rec = (getattr(item, "recommended", "") or "").strip()
            banned = (getattr(item, "banned", "") or "").strip()
            if rec:
                tip = self._short_tip_from(rec, banned=False)
                if tip and tip not in tips:
                    tips.append(tip)
            if banned and len(tips) < 2:
                tip = self._short_tip_from(banned, banned=True)
                if tip and tip not in tips:
                    tips.append(tip)
            if len(tips) >= 2:
                break
        return tips[:2] or ["补问水质与水温", "把下一步收成具体人/时间"]

    def _short_tip_from(self, text: str, *, banned: bool = False) -> str:
        raw = " ".join((text or "").split()).strip()
        if not raw:
            return ""
        parts = [p.strip() for p in re.split(r"[，。；;、,]", raw) if p.strip()]
        if not parts:
            return ""
        if banned:
            # 优先取禁止句，提炼成「勿…」
            pick = next(
                (p for p in parts if re.match(r"^(也?不要|别|不能|禁止|避免|忌|勿)", p)),
                min(parts, key=len),
            )
            pick = re.sub(r"^(也?不要|别|不能|禁止|避免|忌|勿)\s*", "", pick)
            tip = f"勿{pick}"
        else:
            pick = parts[0]
            pick = re.sub(r"^(先|优先|建议)\s*", "", pick)
            pick = re.sub(r"^(确认|问清|了解|说明|介绍)", r"先\1", pick)
            tip = pick if pick.startswith("先") else f"先{pick}"
        tip = tip.strip().strip("。；;.!！")
        return tip[:20] if tip else ""

    def _msg_field(self, msg: Any, name: str, default: Any = "") -> Any:
        if isinstance(msg, dict):
            return msg.get(name, default)
        return getattr(msg, name, default)

    def _live_tip_prompt(self, session: Any, messages: Any, knowledge: Any, context: str = "after_sales") -> str:
        msgs = list(messages or [])
        last_role = self._msg_field(msgs[-1], "role", "") if msgs else ""
        # context 优先：前端明确知道当前是业务员刚说完还是客户刚说完
        if context == "after_customer":
            moment = "客户刚说完，业务员马上要接话"
        elif context == "after_sales":
            moment = "业务员刚说完，客户还在生成/播报"
        else:
            moment = (
                "客户刚说完，业务员马上要接话"
                if last_role == "customer"
                else "业务员刚说完，客户还在生成/播报"
            )
        lines = []
        for msg in msgs[-8:]:
            role = self._msg_field(msg, "role", "")
            content = self._msg_field(msg, "content", "")
            label = "业务员" if role == "sales" else "客户"
            lines.append(f"{label}：{str(content)[:120]}")
        transcript = "\n".join(lines) or "（暂无对话）"
        cards_text = _product_cards_text(session, knowledge if isinstance(knowledge, list) else None)
        cards_block = f"\n产品卡：\n{cards_text}" if cards_text else ""
        return (
            "你是纺织助剂销售陪练的旁路实时教练，场景是固色剂/湿摩擦提升剂/硅油等助剂。"
            f"当前时机：{moment}。请给业务员 1-2 条立刻可做的短提示。\n"
            "只输出 2 行以内，一行一条提示，每条不超过 20 个汉字，不要编号、不要解释、不要 JSON。\n"
            "提示必须贴合下方知识库与当前对话：优先从知识条目 recommended 提炼「先…」动作提示，"
            "从 banned 提炼「勿…」风险提示，不要给与知识无关的通用套话。\n"
            "提示必须可直接照做，可覆盖：工艺探询（水质/水温/工艺/布种）、选型风险（高硬高温勿只推833）、"
            "技术边界（涂料化纤难提升、大货小样差异、同浴沉淀）、推进动作（收成具体人/时间/条件）、禁用话术（勿瞎承诺/勿空泛保证）。\n"
            f"训练：{getattr(session, 'training_type', '')} / {getattr(session, 'stage', '')} / {getattr(session, 'goal', '')}\n"
            f"客户：{getattr(session, 'customer_name', '')} / {getattr(session, 'customer_type', '')}\n"
            f"知识库：\n{_knowledge_text(knowledge) if isinstance(knowledge, list) else ''}\n"
            f"最近对话：\n{transcript}\n"
            f"{cards_block}"
        )

    def _parse_live_tips(self, text: str) -> list[str]:
        raw = _strip_thinking(text or "").strip()
        if not raw:
            return []
        candidate = raw
        if candidate.startswith("```"):
            candidate = candidate.removeprefix("```json").removeprefix("```").strip()
            candidate = candidate.removesuffix("```").strip()
        tips: list[str] = []
        for snippet in (candidate, raw):
            start = snippet.find("[")
            end = snippet.rfind("]")
            if start == -1 or end <= start:
                continue
            try:
                data = json.loads(snippet[start : end + 1])
            except Exception:
                continue
            if isinstance(data, list):
                tips = [str(item).strip() for item in data if str(item).strip()]
                break
        if not tips:
            for line in raw.splitlines():
                line = line.strip()
                if not line:
                    continue
                line = re.sub(r"^[-•*·]?\s*\d+[.、)）:：]\s*", "", line).strip()
                line = line.strip().strip('"“”').strip()
                if line:
                    tips.append(line)
        cleaned = []
        for tip in tips:
            tip = " ".join(str(tip).split()).strip('"“”').strip()
            if not tip:
                continue
            if len(tip) > 40:
                tip = tip[:40]
            cleaned.append(tip)
            if len(cleaned) >= 2:
                break
        return cleaned

    async def analyze_document_metadata(self, filename: str, raw_text: str, fallback: dict[str, Any]) -> dict[str, Any]:
        config = get_effective_llm_config()
        if not self._configured(config):
            return {**fallback, "llm_status": "mock:not_configured"}
        prompt = (
            "你是销售知识库文档分析助手。请根据文件名和正文片段，判断资料类型和适合的检索标签。"
            "只输出合法 JSON 对象，不要 Markdown。\n"
            "JSON 字段：source_type, tags, summary。\n"
            "source_type 只能是 SOP 与话术 或 产品说明书。\n"
            "SOP 与话术可选标签：销售流程、商务谈判、价格异议、异议处理、推荐话术、禁用话术、评分标准、回款交涉。\n"
            "产品说明书可选标签：产品参数、工艺条件、应用场景、使用方法、注意事项、技术边界、价值表达、常见问题。\n"
            "tags 选择 2-5 个最相关标签。summary 用一句话说明判断依据。\n"
            f"文件名：{filename}\n"
            f"解析兜底：{json.dumps(fallback, ensure_ascii=False)}\n"
            f"正文片段：{_excerpt(raw_text, 5000)}"
        )
        try:
            data = await self._chat([{"sender_type": "USER", "text": prompt}], config, max_tokens=700)
            parsed = json.loads(self._json_text(data))
        except Exception as exc:
            return {**fallback, "llm_status": f"mock:analyze_failed:{exc.__class__.__name__}"}
        return self._normalize_document_analysis(parsed, fallback)

    def _report_prompt(
        self,
        session: TrainingSession,
        messages: list[TrainingMessage],
        knowledge: list[KnowledgeItem],
    ) -> str:
        transcript = "\n".join(f"{m.role}: {m.content}" for m in messages) or "商机推进教练无多轮对话，仅基于业务员填写的商机背景生成推进方案。"
        
        # 分析对话统计数据
        sales_messages = [m for m in messages if m.role == "sales"]
        customer_messages = [m for m in messages if m.role == "customer"]
        sales_turns = len(sales_messages)
        avg_sales_length = sum(len(m.content) for m in sales_messages) / max(sales_turns, 1)
        is_opportunity = self._is_opportunity(session)

        # 构建详细的评分标准
        scoring_criteria = self._build_scoring_criteria(
            session, sales_turns, avg_sales_length, is_opportunity=is_opportunity
        )
        score_formula = build_score_formula_text(
            getattr(session, "goal", "") or "", is_opportunity=is_opportunity
        )
        cards_text = _product_cards_text(session, knowledge)
        cards_block = f"\n产品卡（选型/边界/价值参考）：\n{cards_text}\n" if cards_text else ""
        plan = _plan_training_context(session)
        plan_active = _plan_training_active(plan)
        plan_block = ""
        if plan_active:
            focus_lines = _plan_focus_lines(plan)
            plan_block = (
                "\n## 本轮是「针对推进方案的针对性训练」\n"
                "summary / 建议必须对照下列推进方案要点，判断业务员有没有真正推进一步"
                "（尤其是「必须问清」是否问到位、「优先推进动作」是否落地），不要泛泛评价。\n"
                + "\n".join(f"- {line}" for line in focus_lines)
                + "\n- focus_scores 仅作评分参考（偏向薄弱维度的原因说明），不要强制改分，仍按原有 JSON 字段与评分规则输出。\n"
            )

        common = (
            "你是纺织助剂行业销售培训教练（宏昊化工场景：固色剂/湿摩擦提升剂/硅油/前后整理助剂）。"
            "必须基于输入的客户背景、商机阶段、训练目标、产品与工艺知识库生成个性化内容，"
            "不要使用泛泛模板，不要编造未出现的事实。只输出一个合法 JSON 对象，不要 Markdown。\n"
            "固定 JSON 字段：overall_score, summary, scores, good_lines, risk_lines, alternatives, checklist, citations。\n"
            "scores 必须包含 7 项：工艺探询、产品选型、技术边界、异议处理、故障归因、价值合规、推进动作；"
            "每项格式为 {\"name\":\"维度\",\"value\":1-5,\"reason\":\"结合本次内容的具体原因\"}。\n"
            "## 内容契约（good_lines / risk_lines / alternatives 必须遵守）\n"
            "1. good_lines、risk_lines、alternatives 必须结合知识库中的 recommended（推荐话术）、banned（禁用话术）"
            "以及产品卡里的型号/工艺条件/技术边界/认证信息来写，不要脱离资料写空话。\n"
            "2. good_lines：指出业务员说对了什么，优先点出与 recommended 口径一致、或用上了产品卡型号/参数/认证的具体句子。\n"
            "3. risk_lines：指出踩了哪些 banned 禁用口径或技术边界（瞎承诺、型号错配、未问清水质水温就推、"
            "混淆日标/国标、认证乱承诺），要能对应到具体话术。\n"
            "4. alternatives：写成业务员下一轮可直接开口说的纺织助剂话术，口语、完整句子；"
            "尽量含具体型号（如 HT-790/831B/868/833）、工艺条件（用量、温度、浸轧/浸渍、同浴/分浴）、"
            "测试标准（日标/国标、湿摩擦级数）或认证（bluesign/GOTS/OEKO-TEX/ZDHC）；"
            "禁止「加强沟通」「体现价值」这类空话。\n"
            "5. citations 必须指向真实命中的知识库来源：source 必须使用下方知识库条目里的文档名（source:…），"
            "不得编造文档名；reason 写清 chunk_type、章节/页码，以及该片段如何支撑评分或建议。\n"
            "6. 如果知识库为空或明显没有命中，citations 的 reason 写“依据不足”，不要伪造来源。\n"
            "若对话中出现技术/老板入场（客户消息带 [tech]/[boss] 等角色标签），"
            "客户洞察与异议处理可参照多角色表现：技术追问是否接住、老板拍板/底线是否回应。\n\n"
            "## 评分标准（必须严格遵循）\n"
            f"{scoring_criteria}\n\n"
            "## 评分计算规则\n"
            f"{score_formula}\n\n"
            f"训练类型：{session.training_type}\n客户：{session.customer_name} / {session.customer_type}\n"
            f"阶段：{session.stage}\n目标：{session.goal}\n背景：{session.background}\n"
            f"{plan_block}"
            f"知识库：\n{_knowledge_text(knowledge)}\n"
            f"{cards_block}"
            f"对话或输入：\n{transcript}\n"
        )
        if session.training_type == "商机推进教练":
            return (
                common
                + "商机推进教练输出要求：\n"
                + "summary 写成当前商机判断，必须结合阶段、关键阻碍、关键人和最近沟通结果，不超过 80 字；禁止写对话轮次。\n"
                + "good_lines 写 2 条当前有利条件或可利用抓手（可引用最近沟通结果、已有关系、产品/认证优势）。\n"
                + "risk_lines 写 3 条关键风险，必须结合阶段、关键人、阻碍或最近沟通结果，写清风险后果。\n"
                + "alternatives 写 3 条不同角度的交涉策略：卡点复述、关键人推进、条件换承诺；"
                + "每条写成可直接照着说或照着做的完整句子，要带上客户名/阻碍/里程碑等具体信息。\n"
                + "checklist 写 4 个待办对象，格式为 {\"title\":\"具体事项\",\"detail\":\"执行要点（谁做什么、要什么材料/确认什么）\",\"due\":\"1 天内/2 天内/3 天内/5 天内\"}；"
                + "title 不要写成“确认下一步节点”这类空标题，要写清具体对象（如“约品牌端标准确认人对齐测试口径”）。\n"
                + "scores 的 reason 必须引用商机背景中的具体信息，禁止模板套话。\n"
            )
        return (
            common
            + "客户情景陪练输出要求：\n"
            + "summary 写成教练总体评价，不超过 80 字。\n"
            + "good_lines 摘录或改写 2 条本轮表现亮点，尽量点出具体型号、工艺参数、认证或案例，并标明与知识库 recommended 的一致点。\n"
            + "risk_lines 指出 2 条具体话术风险，结合型号错配、边界瞎承诺、水质/工艺未问清、踩到 banned 禁用口径等。\n"
            + "alternatives 给 2-3 条替代话术，必须可直接用于下一次客户沟通，含具体型号、工艺条件、测试标准或认证价值；"
            + "示例味道：「按您说的水温偏高，建议先用 HT-790 做 2g/L 浸轧小样，日标测湿擦，我们出测试报告再谈大货」。\n"
            + "checklist 给 3 个下一轮训练动作，写清可执行条件（如补问水质水温、约工程师定小样条件、准备测试报告）。\n"
            + (
                "若上方存在「针对推进方案的针对性训练」：summary / risk_lines / alternatives / checklist 必须对照 must_ask、"
                "primary_action、checklist 判断有没有推进一步（例如 must_ask 是否问到位、primary_action 是否被推进），"
                "不要写成与推进方案无关的泛泛评价。\n"
                if plan_active
                else ""
            )
        )

    def _build_scoring_criteria(
        self,
        session: TrainingSession,
        sales_turns: int,
        avg_sales_length: float,
        is_opportunity: bool = False,
    ) -> str:
        """评分标准文案来自 scoring 模块（与权重同源）。

        scoring 侧签名可能因 goal 调权而变化，这里只做调用适配，不改 scoring 内部实现。
        """
        try:
            return build_scoring_criteria_text(
                sales_turns=sales_turns,
                avg_sales_length=avg_sales_length,
                goal=session.goal,
                stage=session.stage,
                is_opportunity=is_opportunity,
            )
        except TypeError:
            # 兼容签名变化（新增/改名参数）：按位置参数调用，或退回最小参数集
            try:
                return build_scoring_criteria_text(
                    sales_turns, avg_sales_length, session.goal, session.stage, is_opportunity
                )
            except TypeError:
                try:
                    return build_scoring_criteria_text(sales_turns, avg_sales_length, session.goal, session.stage)
                except TypeError:
                    return build_scoring_criteria_text(sales_turns, avg_sales_length, "", "")

    def _configured(self, config: EffectiveLLMConfig) -> bool:
        return config.configured

    async def test_connection(self, config: EffectiveLLMConfig) -> dict[str, Any]:
        if not self._configured(config):
            return {"ok": False, "message": "模型配置不完整", "model_id": config.model_id, "latency_ms": 0}
        started = time.perf_counter()
        try:
            data = await self._chat(
                [{"sender_type": "USER", "text": "请只回复 OK，用于测试模型连接。"}],
                config,
                max_tokens=32,
            )
        except httpx.HTTPError as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            return {"ok": False, "message": f"模型连接失败：{exc.__class__.__name__}", "model_id": config.model_id, "latency_ms": latency_ms}
        latency_ms = int((time.perf_counter() - started) * 1000)
        if not data.strip():
            return {"ok": False, "message": "模型无有效返回", "model_id": config.model_id, "latency_ms": latency_ms}
        return {"ok": True, "message": "模型连接成功", "model_id": config.model_id, "latency_ms": latency_ms}

    def _provider(self, config: EffectiveLLMConfig):
        return resolve_provider(config.base_url, config.group_id)

    async def _chat(self, messages: list[dict], config: EffectiveLLMConfig, max_tokens: int = 1024) -> str:
        provider = self._provider(config)
        return await provider.chat(messages, config.model_id, config.api_key, max_tokens)

    async def _chat_stream(
        self, messages: list[dict], config: EffectiveLLMConfig, max_tokens: int = 1024
    ) -> AsyncGenerator[str, None]:
        provider = self._provider(config)
        async for chunk in provider.chat_stream(messages, config.model_id, config.api_key, max_tokens):
            yield chunk

    def _openai_messages(self, messages: list[dict]) -> list[dict]:
        return _openai_messages(messages)

    def _anthropic_messages(self, messages: list[dict]) -> tuple[str, list[dict]]:
        return _anthropic_messages(messages)

    def _is_opportunity(self, session: TrainingSession) -> bool:
        return (getattr(session, "training_type", "") or "") == "商机推进教练"

    def _opportunity_context(self, session: TrainingSession) -> dict[str, str]:
        """从 setup_context / background 抽取商机字段，供生成个性化推进方案。"""
        setup = getattr(session, "setup_context", None) or {}
        opp = setup.get("opportunity_setup") if isinstance(setup, dict) else None
        if not isinstance(opp, dict):
            opp = {}
        background = getattr(session, "background", "") or ""
        labels = {
            "last_contact": "最近一次沟通结果",
            "decision_blocker": "关键阻碍",
            "next_milestone": "下一步里程碑",
            "stakeholder": "关键人参与情况",
            "product": "产品",
        }
        parsed: dict[str, str] = {}
        for key, label in labels.items():
            match = re.search(rf"{label}：([^\n]+)", background)
            parsed[key] = match.group(1).strip() if match else ""
        return {
            "customer_name": getattr(session, "customer_name", "") or "当前商机",
            "stage": getattr(session, "stage", "") or "",
            "goal": getattr(session, "goal", "") or "",
            "last_contact": str(opp.get("last_contact") or parsed.get("last_contact") or "").strip(),
            "decision_blocker": str(opp.get("decision_blocker") or parsed.get("decision_blocker") or "").strip(),
            "next_milestone": str(opp.get("next_milestone") or parsed.get("next_milestone") or "").strip(),
            "stakeholder": str(opp.get("stakeholder") or parsed.get("stakeholder") or "").strip(),
            "product": parsed.get("product") or "",
            "background": background,
        }

    async def _repair_json(self, raw: str, config: EffectiveLLMConfig) -> str:
        """JSON 解析失败时，让模型把返回修成合法 JSON，尽量保住生成内容。"""
        prompt = (
            "下面内容本应是合法 JSON 对象，但现在无法解析。"
            "请修复为合法 JSON 对象并只输出 JSON，不要解释、不要 Markdown。\n\n"
            + _excerpt(raw, 6000)
        )
        try:
            return await self._chat([{"sender_type": "USER", "text": prompt}], config, max_tokens=4096)
        except httpx.HTTPError:
            return ""

    def _parse_json_object(self, text: str) -> dict[str, Any] | None:
        if not text or not text.strip():
            return None
        candidates = [self._json_text(text)]
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = stripped.removeprefix("```json").removeprefix("```").strip()
            stripped = stripped.removesuffix("```").strip()
            candidates.append(stripped)
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidates.append(stripped[start : end + 1])
        for candidate in candidates:
            if not candidate:
                continue
            try:
                data = json.loads(candidate)
            except Exception:
                continue
            if isinstance(data, dict):
                return data
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and any(k in item for k in ("summary", "scores", "overall_score")):
                        return item
        # 兜底：去掉尾逗号再试
        for candidate in candidates:
            if not candidate:
                continue
            cleaned = re.sub(r",\s*([}\]])", r"\1", candidate)
            try:
                data = json.loads(cleaned)
            except Exception:
                continue
            if isinstance(data, dict):
                return data
        return None

    def _json_text(self, text: str) -> str:
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = stripped.removeprefix("```json").removeprefix("```").strip()
            stripped = stripped.removesuffix("```").strip()
        if not stripped.startswith("{"):
            start = stripped.find("{")
            end = stripped.rfind("}")
            if start != -1 and end != -1 and end > start:
                stripped = stripped[start : end + 1]
        return stripped

    def _normalize_document_analysis(self, data: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
        allowed_types = {"SOP 与话术", "产品说明书"}
        tag_presets = {
            "SOP 与话术": {"销售流程", "商务谈判", "价格异议", "异议处理", "推荐话术", "禁用话术", "评分标准", "回款交涉"},
            "产品说明书": {"产品参数", "工艺条件", "应用场景", "使用方法", "注意事项", "技术边界", "价值表达", "常见问题"},
        }
        source_type = data.get("source_type") if data.get("source_type") in allowed_types else fallback.get("source_type")
        source_type = source_type if source_type in allowed_types else "SOP 与话术"
        raw_tags = data.get("tags") if isinstance(data.get("tags"), list) else []
        tags = [item for item in raw_tags if isinstance(item, str) and item in tag_presets[source_type]]
        if not tags:
            tags = fallback.get("tags") or []
        return {
            **fallback,
            "source_type": source_type,
            "tags": tags[:5],
            "summary": self._text(data.get("summary"), fallback.get("summary", "已完成文档预分析。")),
            "llm_status": "llm",
        }

    def _normalize_report(
        self,
        data: dict[str, Any],
        session: TrainingSession,
        knowledge: list[KnowledgeItem],
    ) -> dict[str, Any]:
        is_opportunity = self._is_opportunity(session)
        fallback = self._mock_report(session, [], knowledge)
        source = knowledge[0].source_name if knowledge else ("商机推进规范" if is_opportunity else "模拟销售 SOP")
        source_reason = f"用于判断“{session.stage} / {session.goal}”场景下的推荐动作和禁用话术。"

        scores = data.get("scores")
        if not isinstance(scores, list) or len(scores) < 7:
            scores = fallback["scores"]
        else:
            scores = [self._score_item(item, fallback["scores"][index]) for index, item in enumerate(scores[:7])]

        sales_texts = [
            getattr(m, "content", "") or ""
            for m in (getattr(session, "messages", None) or [])
            if getattr(m, "role", "") == "sales"
        ]
        if not sales_texts:
            sales_texts = [
                (m.get("content", "") if isinstance(m, dict) else getattr(m, "content", ""))
                for m in (getattr(session, "messages", None) or [])
                if (m.get("role") if isinstance(m, dict) else getattr(m, "role", "")) == "sales"
            ]
        # 商机推进方案没有业务员对话，不能用“没问水质/没下一步”打对话硬约束
        if not is_opportunity:
            scores = enforce_hard_caps(scores, sales_texts)

        # 重新计算overall_score，确保符合（可按 goal 调整的）权重规则
        overall_score = self._calculate_overall_score(scores, session, is_opportunity=is_opportunity)

        knowledge_sources = {item.source_name for item in knowledge if item.source_name}
        citations = data.get("citations")
        if not isinstance(citations, list) or not citations:
            citations = []
        else:
            citations = [self._citation_item(item, source, source_reason, knowledge_sources) for item in citations[:4]]
        # 过滤内部状态类条目，不进用户可见引用依据
        citations = [
            item
            for item in citations
            if item.get("source") not in {"LLM 调用状态", "LLM调用状态"} and not str(item.get("source", "")).startswith("mock:")
        ]
        if knowledge_sources and not any(item["source"] in knowledge_sources for item in citations):
            citations.insert(0, {"source": source, "reason": source_reason})
        if not citations:
            citations = [{"source": source, "reason": source_reason}]

        normalized = {
            "overall_score": overall_score,
            "summary": self._text(data.get("summary"), fallback["summary"]),
            "scores": scores,
            "good_lines": self._text_list(data.get("good_lines"), fallback["good_lines"], 2),
            "risk_lines": self._text_list(data.get("risk_lines"), fallback["risk_lines"], 2),
            "alternatives": self._text_list(data.get("alternatives"), fallback["alternatives"], 3),
            "checklist": self._text_list(data.get("checklist"), fallback["checklist"], 3),
            "citations": citations,
        }
        if is_opportunity:
            normalized = self._normalize_opportunity_report(normalized, session, knowledge)
        return normalized

    def _calculate_overall_score(
        self,
        scores: list[dict[str, Any]],
        session: TrainingSession,
        is_opportunity: bool = False,
    ) -> int:
        """总分由 scoring 模块统一计算（与 prompt 权重同源）。"""
        try:
            sales_turns = len(
                [m for m in (getattr(session, "messages", None) or []) if getattr(m, "role", "") == "sales"]
            )
        except Exception:
            sales_turns = 3 if not is_opportunity else MIN_SALES_TURNS_FOR_FULL_SCORE
        if is_opportunity and sales_turns <= 0:
            sales_turns = MIN_SALES_TURNS_FOR_FULL_SCORE
        goal = getattr(session, "goal", "") or ""
        return calculate_overall_score(
            scores,
            sales_turns=sales_turns,
            goal=goal,
            is_opportunity=is_opportunity,
        )

    def _normalize_opportunity_report(
        self,
        data: dict[str, Any],
        session: TrainingSession,
        knowledge: list[KnowledgeItem],
    ) -> dict[str, Any]:
        ctx = self._opportunity_context(session)
        blocker = ctx.get("decision_blocker") or "当前关键阻碍"
        milestone = ctx.get("next_milestone") or "下一步里程碑"
        stakeholder = ctx.get("stakeholder") or "关键人"
        customer = ctx.get("customer_name") or "客户"
        goal = ctx.get("goal") or "推进商机"
        product = ctx.get("product") or "现有方案"

        actions = self._text_list(data.get("alternatives"), [], 4)
        checklist = data.get("checklist") if isinstance(data.get("checklist"), list) else []
        # 已是对象的 checklist 直接保留，不做标题覆盖
        object_items = [item for item in checklist if isinstance(item, dict)]
        string_items = [item for item in checklist if isinstance(item, str) and str(item).strip()]

        default_actions = [
            f"先复述「{blocker}」的卡点，再确认：这件事谁判断、何时反馈、我们要补什么材料？",
            f"不要只跟单一联系人推进，按「{stakeholder}」拆出采购/技术/决策人的关注点，约齐对齐会。",
            f"把补资料、试样或价格条件绑定到客户对「{milestone}」的明确承诺上。",
            f"把时间、人员、资料或测试条件写成一个可跟进动作，服务目标「{goal}」。",
        ]
        if len(actions) < 4:
            actions.extend(default_actions[len(actions) :])
        actions = actions[:4]

        default_todos = [
            {
                "title": f"约齐「{blocker}」决策人",
                "detail": f"确认谁判断、谁给反馈；把{stakeholder}写进参会名单，约 30 分钟对齐「{milestone}」。",
                "due": "1 天内",
            },
            {
                "title": f"拆解「{milestone}」验收条件",
                "detail": f"明确材料清单、测试口径和时间点，避免目标「{goal}」停留在口号。",
                "due": "2 天内",
            },
            {
                "title": f"补齐{product}证据包",
                "detail": "准备小样条件、测试标准（日标/国标）和第三方报告/客户案例，支撑替换与价格谈判。",
                "due": "3 天内",
            },
            {
                "title": f"固化对{customer}的跟进升级",
                "detail": "设定下次触达时间；无反馈则升级到能拍板的人，不把跟进停留在“保持沟通”。",
                "due": "5 天内",
            },
        ]

        merged_todos: list[dict[str, str]] = []
        generic_titles = {"确认下一步节点", "拆解关键阻碍", "补齐关键人", "固化跟进动作"}
        for index in range(4):
            if index < len(object_items):
                item = object_items[index]
                detail = self._text(
                    item.get("detail") or item.get("content") or item.get("task"),
                    default_todos[index]["detail"],
                )
                raw_title = self._text(item.get("title") or item.get("name"), "")
                title = (
                    raw_title
                    if (len(raw_title) >= 6 and raw_title not in generic_titles)
                    else default_todos[index]["title"]
                )
                merged_todos.append(
                    {
                        "title": title,
                        "detail": detail,
                        "due": self._text(item.get("due") or item.get("deadline") or item.get("time"), default_todos[index]["due"]),
                    }
                )
            elif index < len(string_items):
                merged_todos.append(
                    {
                        "title": default_todos[index]["title"],
                        "detail": self._text(string_items[index], default_todos[index]["detail"]),
                        "due": default_todos[index]["due"],
                    }
                )
            else:
                merged_todos.append(default_todos[index])

        stage_label = ctx.get("stage") or getattr(session, "stage", "") or "当前"
        data["summary"] = self._text(
            data.get("summary"),
            f"{customer}处于“{stage_label}”阶段，卡在“{blocker}”，"
            f"下一步应围绕“{milestone}”把人、时间和条件一次定清。",
        )
        # summary 里若误写对话轮次，替换掉
        if "对话轮次不足" in data["summary"]:
            data["summary"] = (
                f"{customer}处于“{stage_label}”阶段，卡在“{blocker}”。"
                f"下一步围绕“{milestone}”确认责任人、时间点和判断标准。"
            )

        data["alternatives"] = actions[:4]
        data["checklist"] = merged_todos[:4]
        if not data["citations"]:
            source = knowledge[0].source_name if knowledge else "商机推进规范"
            data["citations"] = [{"source": source, "reason": "用于判断推进动作、关键风险和禁用话术。"}]
        return data

    def _todo_item(self, item: Any, index: int, actions: list[str]) -> dict[str, str]:
        titles = ["确认下一步节点", "拆解关键阻碍", "补齐关键人", "固化跟进动作"]
        dues = ["1 天内", "2 天内", "3 天内", "5 天内"]
        if isinstance(item, dict):
            detail = self._text(item.get("detail") or item.get("content") or item.get("task"), actions[index])
            return {
                "title": self._text(item.get("title"), titles[index]),
                "detail": detail,
                "due": self._text(item.get("due") or item.get("deadline"), dues[index]),
            }
        return {
            "title": titles[index],
            "detail": self._text(item, actions[index]),
            "due": dues[index],
        }

    def _score_item(self, item: Any, fallback: dict[str, Any]) -> dict[str, Any]:
        return normalize_score_item(item, fallback)

    def _citation_item(
        self,
        item: Any,
        source: str,
        reason: str,
        knowledge_sources: set[str] | None = None,
    ) -> dict[str, str]:
        if not isinstance(item, dict):
            return {"source": source, "reason": reason}
        raw_source = self._text(item.get("source"), source)
        # citations 必须指向真实命中来源：对不上知识库文档名时，尝试模糊回填
        if knowledge_sources:
            if raw_source in knowledge_sources:
                matched = raw_source
            else:
                matched = next(
                    (
                        name
                        for name in knowledge_sources
                        if name in raw_source or raw_source in name
                    ),
                    None,
                )
            if matched:
                raw_source = matched
            elif source in knowledge_sources:
                raw_source = source
        return {
            "source": raw_source,
            "reason": self._text(item.get("reason"), reason),
        }

    def _text_list(self, value: Any, fallback: list[Any], minimum: int) -> list[Any]:
        if isinstance(value, list):
            items = [item for item in value if item]
        elif isinstance(value, str) and value.strip():
            items = [value.strip()]
        else:
            items = []
        if len(items) < minimum:
            items.extend(fallback[len(items):minimum])
        return items

    def _text(self, value: Any, fallback: str) -> str:
        if isinstance(value, str) and value.strip():
            return value.strip()
        return fallback

    def _score_value(self, value: Any, fallback: int, maximum: int) -> int:
        try:
            score = int(value)
        except (TypeError, ValueError):
            score = fallback
        return max(1, min(maximum, score))

    def _mock_customer_reply(self, session: TrainingSession, messages: list[TrainingMessage]) -> str:
        sales_turns = [m for m in messages if self._msg_field(m, "role", "") == "sales"]
        concern = getattr(session, "customer_concern", "") or "供应稳定"
        difficulty = getattr(session, "customer_difficulty", "") or "标准"
        personality = getattr(session, "customer_personality", "") or "谨慎型"

        if concern == "价格":
            opening = "价格和预算是我现在最关注的点"
        elif concern == "交期":
            opening = "交期能不能保证是我现在最担心的点"
        elif concern == "品质":
            opening = "品质稳定性和返工风险我需要先确认"
        elif concern == "环保合规":
            opening = "环保认证和残留指标我必须先看清楚"
        elif concern == "工艺适配":
            opening = "工艺能不能配上、会不会出问题，我得先确认"
        elif concern == "供应稳定":
            opening = "我们现在供应商挺稳定的，换供应商风险太大"
        else:
            opening = "售后响应和后续服务我需要先看清楚"

        if difficulty == "高压":
            pressure = "如果没有更明确的保障或依据，我很难继续推进。"
        elif difficulty == "刁钻":
            pressure = "你现在的说法还不够具体，我需要看到依据。"
        else:
            pressure = "你可以先把对我们实际有利的部分讲清楚。"

        if personality == "敷衍型":
            pressure = "我时间不多，你直接说重点。"
        elif personality == "专业型":
            pressure = "最好能给到数据、案例或测试条件。"
        elif personality == "压价型":
            pressure = "如果价格没有空间，后面就不用谈了。"

        plan = _plan_training_context(session)
        if _plan_training_active(plan) and not self._is_opportunity(session):
            must_ask = plan.get("must_ask") or ""
            primary_action = plan.get("primary_action") or ""
            focus = must_ask or primary_action
            if len(sales_turns) <= 1:
                if must_ask:
                    return f"[buyer]{opening}。特别是「{must_ask}」，你先说清楚，别急着往下走。"
                return f"[buyer]{opening}。{pressure}"
            if len(sales_turns) == 2:
                if must_ask and primary_action:
                    return f"[buyer]「{must_ask}」你还是没问到位，「{primary_action}」怎么落我这边没法放行。"
                if must_ask:
                    return f"[buyer]「{must_ask}」我还没听明白，你先把这个说清楚再谈下一步。"
                return f"[buyer]围绕「{primary_action}」你准备怎么安排？条件、时间、谁负责，说清楚。"
            if focus:
                return f"[buyer]要继续推进，先把「{focus}」相关条件和责任人说清，否则我这边很难排优先级。"
            return f"[buyer]如果要继续推进，请把{concern}相关的条件、时间和负责人说清楚，否则我这边很难排优先级。"

        if len(sales_turns) <= 1:
            return f"[buyer]{opening}。{pressure}"
        if len(sales_turns) == 2:
            return f"[buyer]听起来有点道理，但围绕{concern}我还没被说服。下一步你准备怎么安排？"
        return f"[buyer]如果要继续推进，请把{concern}相关的条件、时间和负责人说清楚，否则我这边很难排优先级。"

    def _mock_opportunity_report(
        self,
        session: TrainingSession,
        knowledge: list[KnowledgeItem],
    ) -> dict:
        """商机推进方案兜底：必须结合业务员填写的字段，禁止写对话轮次。"""
        ctx = self._opportunity_context(session)
        source = knowledge[0].source_name if knowledge else "商机推进规范"
        customer = ctx["customer_name"]
        stage = ctx["stage"] or "当前阶段"
        goal = ctx["goal"] or "推进商机"
        blocker = ctx["decision_blocker"] or "关键阻碍"
        milestone = ctx["next_milestone"] or "下一步里程碑"
        stakeholder = ctx["stakeholder"] or "关键人参与情况"
        last_contact = ctx["last_contact"] or "最近沟通结果"
        product = ctx["product"] or "现有方案"

        summary = (
            f"{customer}处于「{stage}」，卡在「{blocker}」。"
            f"下一步应围绕「{milestone}」把人、时间和条件一次定清。"
        )

        # 推进成熟度：看关键信息是否齐全、是否可执行
        completeness = 0
        for value in (ctx["decision_blocker"], ctx["next_milestone"], ctx["stakeholder"], ctx["last_contact"]):
            if value:
                completeness += 1
        maturity = 40 + completeness * 8
        if "未参与" in blocker or "未完成" in blocker:
            maturity = min(maturity, 62)
        if completeness >= 4:
            maturity = max(maturity, 68)
        maturity = max(35, min(88, maturity))

        # 七维：结合商机字段写具体 reason，而不是对话关键词
        scores = [
            {
                "name": "工艺探询",
                "value": 3 if completeness < 3 else 4,
                "reason": f"围绕{product}还需补齐水质/水温/使用工艺/布种；当前背景未写全测试口径，方案应先补问再定试样条件。",
            },
            {
                "name": "产品选型",
                "value": 3 if not product else 4,
                "reason": f"已锁定方向「{product}」，但未针对客户已知条件说明取舍（高稳 831B/868 vs 通用款）与备选。",
            },
            {
                "name": "技术边界",
                "value": 3,
                "reason": "推进方案需写清涂料/化纤难提升、大货小样差异、同浴沉淀风险，避免为冲进度做绝对化承诺。",
            },
            {
                "name": "异议处理",
                "value": 3 if blocker else 2,
                "reason": f"针对「{blocker}」应准备带参数/测试标准/案例的回应，而不是安抚话术。",
            },
            {
                "name": "故障归因",
                "value": 3,
                "reason": "若客户此前有斑/色变/气味顾虑，应先按水质、残留、同浴、温度归因，再谈责任与整改。",
            },
            {
                "name": "价值合规",
                "value": 3,
                "reason": "价值表达要落到 bluesign/GOTS/OEKO-TEX/ZDHC 与省水省时、批次稳定，而不是只谈价格。",
            },
            {
                "name": "推进动作",
                "value": 4 if milestone else 2,
                "reason": f"目标「{milestone}」需要落成责任人+时间点+资料/测试条件；当前还需确认谁拍板、谁反馈。",
            },
        ]

        good_lines = []
        if last_contact:
            good_lines.append(f"最近沟通已有锚点：{last_contact}，可据此复述卡点再提条件。")
        if product:
            good_lines.append(f"产品方向已明确（{product}），比泛泛介绍更容易收敛到试样条件。")
        if stakeholder:
            good_lines.append(f"关键人线索：{stakeholder}，可设计分角色推进路径。")
        if not good_lines:
            good_lines.append("商机背景已填写，具备推进方案成型条件。")

        risk_lines = [
            f"「{blocker}」未拆成可验证动作时，{customer}内部容易继续空转。",
            f"若不确认谁最终拍板（{stakeholder or '关键人'}），承诺很难落地。",
            f"围绕「{milestone}」若只说保持沟通，没有时间/材料/测试条件，推进会反复拖延。",
        ]

        alternatives = [
            f"卡点复述：上次谈到「{last_contact}」，这次我们先把「{blocker}」确认成可验证的下一步——您看这件事谁判断、什么时候能给反馈？",
            f"关键人推进：按目前「{stakeholder}」的情况，建议约采购+技术一起过「{milestone}」的条件，避免单线程等回复。",
            f"条件换承诺：我们把{product}的试样/测试资料补齐，换您这边确认「{milestone}」的时间和参会人，可以吗？",
        ]

        checklist = [
            {
                "title": f"约齐「{blocker}」相关决策人",
                "detail": f"确认谁判断「{blocker}」、谁给反馈；把{stakeholder or '采购/技术/老板'}写进参会名单，并约 30 分钟对齐会。",
                "due": "1 天内",
            },
            {
                "title": f"把「{milestone}」拆成可验收条件",
                "detail": f"明确完成标准（材料清单/测试口径/时间点），对应目标「{goal}」，避免里程碑停留在口号。",
                "due": "2 天内",
            },
            {
                "title": f"补齐{product}试样与证据包",
                "detail": "准备小样条件（用量、温度、浸轧/浸渍）、测试标准（日标/国标）和第三方报告/客户案例，便于回应价格与替换风险。",
                "due": "3 天内",
            },
            {
                "title": "固化跟进与升级路径",
                "detail": f"基于「{last_contact}」设定下一次触达时间；若 {customer} 内部无反馈，约定升级到能拍板的人。",
                "due": "5 天内",
            },
        ]

        citations = [
            {
                "source": source,
                "reason": f"用于判断“{stage} / {goal}”下的推进动作、关键风险和禁用话术。",
            }
        ]

        return {
            "overall_score": maturity,
            "summary": summary,
            "scores": scores,
            "good_lines": good_lines[:2],
            "risk_lines": risk_lines[:3],
            "alternatives": alternatives[:3],
            "checklist": checklist[:4],
            "citations": citations,
        }

    def _mock_report(
        self,
        session: TrainingSession,
        messages: list[TrainingMessage],
        knowledge: list[KnowledgeItem],
    ) -> dict:
        if self._is_opportunity(session):
            return self._mock_opportunity_report(session, knowledge)
        source = knowledge[0].source_name if knowledge else "模拟销售 SOP"
        plan = _plan_training_context(session)
        plan_active = _plan_training_active(plan)
        must_ask = plan.get("must_ask") or ""
        primary_action = plan.get("primary_action") or ""
        plan_summary = plan.get("plan_summary") or ""

        # 分析对话内容
        sales_messages = [m for m in messages if self._msg_field(m, "role", "") == "sales"]
        customer_messages = [m for m in messages if self._msg_field(m, "role", "") == "customer"]
        sales_turns = len(sales_messages)
        
        # 提取关键信息
        has_next_step = False
        has_value_expression = False
        has_objection_handling = False
        has_clarification = False
        
        # 分析销售人员的表现
        for msg in sales_messages:
            content = str(self._msg_field(msg, "content", "")).lower()
            # 检查是否有下一步动作
            if any(keyword in content for keyword in ["下一步", "接下来", "安排", "约定", "确认", "安排"]):
                has_next_step = True
            # 检查是否有价值表达
            if any(keyword in content for keyword in ["优势", "价值", "好处", "利益", "帮助"]):
                has_value_expression = True
            # 检查是否有异议处理
            if any(keyword in content for keyword in ["理解", "明白", "但是", "不过", "然而", "虽然"]):
                has_objection_handling = True
            # 检查是否有需求澄清
            if any(keyword in content for keyword in ["请问", "能否", "是否", "需要", "想要", "希望"]):
                has_clarification = True
        
        # 根据对话轮次和表现计算分数
        base_score = 60
        if sales_turns >= 3:
            base_score += 10
        if sales_turns >= 5:
            base_score += 5
        if has_next_step:
            base_score += 10
        if has_value_expression:
            base_score += 5
        if has_objection_handling:
            base_score += 5
        if has_clarification:
            base_score += 5
        
        # 限制分数范围（不做 60 分下限，避免硬约束失效）
        overall_score = min(100, max(0, base_score))
        if sales_turns < 3:
            overall_score = min(overall_score, 70)
        
        # 根据表现生成个性化评分（纺织助剂行业七维）
        scores = []

        # 工艺探询评分
        craft_score = 3
        craft_reason = "问了部分条件，但水质/水温/工艺中仍有两项以上未确认。"
        if has_clarification:
            craft_score = 4
            craft_reason = "问清了主要工艺条件，但测试标准或布种仍有遗漏。"
        if sales_turns >= 3 and has_clarification:
            craft_score = 5
            craft_reason = "能系统问清水质、水温、工艺等关键条件并据此收敛推荐。"
        scores.append({"name": "工艺探询", "value": craft_score, "reason": craft_reason})

        # 产品选型评分
        select_score = 3
        select_reason = "推了通用款，未针对水质/水温/布种等已知条件做差异化选型。"
        if has_value_expression:
            select_score = 4
            select_reason = "选型基本匹配，但未说明取舍理由或备选方案。"
        scores.append({"name": "产品选型", "value": select_score, "reason": select_reason})

        # 技术边界评分
        boundary_score = 3
        boundary_reason = "提到技术局限但含糊，需更明确涂料/化纤、大货小样差异与同浴风险。"
        if has_objection_handling:
            boundary_score = 4
            boundary_reason = "说明了主要技术边界，但个别风险未点透。"
        scores.append({"name": "技术边界", "value": boundary_score, "reason": boundary_reason})

        # 异议处理评分
        objection_score = 3
        objection_reason = "尝试回应异议，但缺乏参数、测试标准或案例支撑。"
        if has_objection_handling:
            objection_score = 4
            objection_reason = "回应了异议，但证据不够贴合客户场景。"
        scores.append({"name": "异议处理", "value": objection_score, "reason": objection_reason})

        # 故障归因评分
        fault_score = 3
        fault_reason = "故障场景归因意识一般，需先查水质、残留、同浴、温度再定责。"
        if has_clarification and has_objection_handling:
            fault_score = 4
            fault_reason = "能做一定归因，但排查路径还可以更完整。"
        scores.append({"name": "故障归因", "value": fault_score, "reason": fault_reason})

        # 价值合规评分
        value_score = 3
        value_reason = "价值表达偏泛，需结合 bluesign/GOTS/OEKO-TEX/ZDHC 认证与省水省时稳定性。"
        if has_value_expression:
            value_score = 4
            value_reason = "表达了合规或效率价值，但与客户账算得不够细。"
        scores.append({"name": "价值合规", "value": value_score, "reason": value_reason})

        # 推进动作评分
        action_score = 3
        action_reason = "下一步动作还不够具体，需收敛到试样条件、工程师与人/时间/条件。"
        if has_next_step:
            action_score = 4
            action_reason = "有下一步动作，但缺少责任人或具体小样条件。"
        scores.append({"name": "推进动作", "value": action_score, "reason": action_reason})
        
        # 生成个性化总结
        summary = "本轮能回应客户问题，但推进动作还需要更明确，建议把下一步收敛到关键人、时间和测试条件。"
        if sales_turns < 3:
            summary = "对话轮次不足，建议至少完成3轮对话以获得更全面的评估。"
        elif has_next_step and has_value_expression:
            summary = "本轮表现良好，能明确下一步动作并表达价值，建议继续加强需求澄清和异议处理。"
        elif has_next_step:
            summary = "能明确下一步动作，但价值表达和需求澄清还需要加强。"
        elif has_value_expression:
            summary = "能表达价值，但缺少明确的下一步动作，建议把对话收敛到具体行动。"

        if plan_active:
            focus_bits = []
            if must_ask:
                focus_bits.append(f"必须问清「{must_ask}」")
            if primary_action:
                focus_bits.append(f"推进「{primary_action}」")
            focus_text = "，".join(focus_bits) or "推进方案焦点"
            if sales_turns < 3:
                summary = f"本轮是针对推进方案的针对性训练，对话轮次不足；请对照{focus_text}完成问清与推进后再复盘。"
            elif has_next_step:
                summary = f"本轮是针对推进方案的针对性训练，已有下一步动作，但仍需对照{focus_text}确认是否真正推进一步。"
            else:
                summary = f"本轮是针对推进方案的针对性训练，尚未对照{focus_text}推进一步，建议先把方案焦点问透再收下一步。"

        # 生成个性化亮点
        good_lines = []
        if has_next_step:
            good_lines.append("能明确提出下一步动作，推动对话进展。")
        if has_value_expression:
            good_lines.append("能结合客户需求表达产品价值。")
        if has_objection_handling:
            good_lines.append("能有效回应客户异议，保持对话流畅。")
        if not good_lines:
            good_lines.append("能保持对话连贯性，回应客户问题。")
        if plan_active and must_ask and has_clarification:
            good_lines.append(f"能围绕「{must_ask}」追问澄清，贴合推进方案要求。")

        # 生成个性化风险点
        risk_lines = []
        if not has_next_step:
            risk_lines.append("缺少明确的下一步动作，容易让商机停滞。")
        if not has_clarification:
            risk_lines.append("需求澄清不足，可能遗漏客户真实需求。")
        if not has_objection_handling:
            risk_lines.append("异议处理不够充分，可能影响客户决策。")
        if not risk_lines:
            risk_lines.append("后续保持沟通这类说法太虚，容易让商机继续停滞。")
        if plan_active:
            if must_ask and not has_clarification:
                risk_lines.insert(0, f"未问清「{must_ask}」，业务员若不问到位不应放行下一步。")
            if primary_action and not has_next_step:
                risk_lines.insert(0, f"未推进「{primary_action}」，推进方案焦点尚未落地。")
            if must_ask and has_clarification and primary_action and has_next_step and len(risk_lines) < 2:
                risk_lines.append(f"对照「{must_ask}」/「{primary_action}」还需把责任人、时间、条件收成可跟进动作。")

        # 生成个性化建议
        alternatives = []
        if not has_next_step:
            alternatives.append("建议改成：我们先约技术和采购一起确认测试条件，您看周三下午是否方便？")
        if not has_clarification:
            alternatives.append("建议增加需求澄清问题：您最关注的是稳定性、成本还是交付周期？")
        if not has_objection_handling:
            alternatives.append("建议回应异议时提供更多证据：我们有第三方检测报告和客户案例。")
        if not alternatives:
            alternatives.append("建议把下一步收敛为明确的人员、时间和条件。")
        if plan_active:
            if must_ask:
                alternatives.insert(0, f"建议改成可开口的推进话术：关于「{must_ask}」，我先把条件跟您对齐，确认完再约下一步时间。")
            if primary_action and not has_next_step:
                alternatives.append(f"建议按「{primary_action}」收成具体人/时间/条件，不要停留在保持沟通。")

        # 生成个性化任务清单
        checklist = []
        if not has_next_step:
            checklist.append("确认关键人")
        if not has_clarification:
            checklist.append("补充需求澄清问题")
        if not has_objection_handling:
            checklist.append("准备异议处理话术")
        checklist.append("约定下一次沟通时间")
        checklist.append("补充测试或成本依据")
        if plan_active:
            plan_items = []
            if must_ask:
                plan_items.append(f"问清「{must_ask}」")
            if primary_action:
                plan_items.append(f"推进「{primary_action}」")
            for item in plan.get("checklist") or []:
                title = (item.get("title") or "").strip()
                if title:
                    plan_items.append(title)
            checklist = plan_items + checklist

        return {
            "overall_score": overall_score,
            "summary": summary,
            "scores": scores,
            "good_lines": good_lines[:2],
            "risk_lines": risk_lines[:2],
            "alternatives": alternatives[:3],
            "checklist": checklist[:3],
            "citations": [{"source": source, "reason": "用于判断推荐话术和禁用话术。"}],
        }
