import json
import logging
import time
from typing import Any

import httpx

from app.models import KnowledgeItem, TrainingMessage, TrainingSession
from app.services.llm_config import EffectiveLLMConfig, get_effective_llm_config

logger = logging.getLogger(__name__)


def _strip_thinking(text: str) -> str:
    stripped = (text or "").strip()
    while stripped.startswith("<think>"):
        end = stripped.find("</think>")
        if end == -1:
            return stripped
        stripped = stripped[end + len("</think>") :].strip()
    return stripped


def _excerpt(text: str, limit: int = 700) -> str:
    return " ".join((text or "").split())[:limit]


def _knowledge_text(items: list[KnowledgeItem]) -> str:
    lines = []
    for item in items:
        location = item.section_title or "未标注章节"
        if item.page_start and item.page_end and item.page_end != item.page_start:
            location = f"{location} / 第 {item.page_start}-{item.page_end} 页"
        elif item.page_start:
            location = f"{location} / 第 {item.page_start} 页"
        lines.append(
            "- "
            f"source:{item.source_name}; doc_type:{item.source_type}; chunk_type:{item.chunk_type}; "
            f"section:{location}; confidence:{item.confidence}; stage:{item.stage}; scenario:{item.scenario}; "
            f"recommended:{item.recommended}; banned:{item.banned}; content:{_excerpt(item.content)}"
        )
    return "\n".join(lines)


def _customer_profile_text(session: TrainingSession) -> str:
    difficulty = getattr(session, "customer_difficulty", "") or "标准"
    personality = getattr(session, "customer_personality", "") or "谨慎型"
    concern = getattr(session, "customer_concern", "") or "价格"
    return f"客户难度：{difficulty}；客户性格：{personality}；核心关注：{concern}"


class LLMClient:
    async def customer_reply(
        self,
        session: TrainingSession,
        messages: list[TrainingMessage],
        knowledge: list[KnowledgeItem],
    ) -> str:
        config = get_effective_llm_config()
        if not self._configured(config):
            return self._mock_customer_reply(session, messages)

        prompt = (
            "你是一个真实客户，正在和业务员进行销售陪练。"
            "不要轻易被说服，要围绕客户背景、商机阶段和训练目标持续追问。"
            "每次回复控制在 80 字以内，像客户自然说话。\n"
            "客户回复必须体现客户难度、性格和核心关注点，不要过早让步。\n"
            f"训练类型：{session.training_type}\n商机阶段：{session.stage}\n目标：{session.goal}\n"
            f"客户：{session.customer_name} / {session.customer_type}\n"
            f"{_customer_profile_text(session)}\n"
            f"背景：{session.background}\n"
            f"可参考资料：\n{_knowledge_text(knowledge)}"
        )
        history = [{"sender_type": "BOT", "text": prompt}]
        for msg in messages[-8:]:
            sender = "USER" if msg.role == "sales" else "BOT"
            history.append({"sender_type": sender, "text": msg.content})
        try:
            data = await self._chat(history, config, max_tokens=1024)
        except httpx.HTTPError:
            data = ""
        return data or self._mock_customer_reply(session, messages)

    async def score_report(
        self,
        session: TrainingSession,
        messages: list[TrainingMessage],
        knowledge: list[KnowledgeItem],
    ) -> dict:
        config = get_effective_llm_config()
        if not self._configured(config):
            report = self._mock_report(session, messages, knowledge)
            report["llm_status"] = "mock:not_configured"
            return self._normalize_report(report, session, knowledge)

        prompt = self._report_prompt(session, messages, knowledge)
        try:
            data = await self._chat([{"sender_type": "USER", "text": prompt}], config, max_tokens=1400)
            llm_status = "llm"
        except httpx.HTTPError as exc:
            data = ""
            llm_status = f"mock:http_error:{exc.__class__.__name__}"
        try:
            parsed = json.loads(self._json_text(data))
        except Exception:
            parsed = self._mock_report(session, messages, knowledge)
            parsed["llm_status"] = f"mock:invalid_json:{llm_status}"
        else:
            parsed["llm_status"] = llm_status
        return self._normalize_report(parsed, session, knowledge)

    async def suggested_reply(
        self,
        session: TrainingSession,
        messages: list[TrainingMessage],
        knowledge: list[KnowledgeItem],
    ) -> str:
        last_customer = next((msg.content for msg in reversed(messages) if msg.role == "customer"), "")
        fallback = (
            "我理解您的顾虑。为了避免只停留在口头沟通，我建议我们先确认关键条件、责任人和下一次沟通时间，"
            "再根据测试结果或商务边界推进下一步。"
        )
        config = get_effective_llm_config()
        if not self._configured(config):
            return fallback
        transcript = "\n".join(f"{m.role}: {m.content}" for m in messages[-8:])
        prompt = (
            "你是销售话术教练。请根据当前训练上下文，给业务员生成一条可参考的下一句回复。"
            "要求：只输出一句自然口语化回复，不要解释，不要编号；必须回应客户刚才的问题，并推动一个明确下一步。"
            "不要承诺无法确认的数据，不要直接降价，不要说空泛的保持沟通。控制在 80 字以内。\n"
            f"客户最后一句：{last_customer}\n"
            f"训练类型：{session.training_type}\n阶段：{session.stage}\n目标：{session.goal}\n"
            f"客户：{session.customer_name} / {session.customer_type}\n背景：{session.background}\n"
            f"知识库：\n{_knowledge_text(knowledge)}\n"
            f"最近对话：\n{transcript}"
        )
        try:
            data = await self._chat([{"sender_type": "USER", "text": prompt}], config, max_tokens=1024)
        except httpx.HTTPError:
            return fallback
        return data.strip().strip('"“”') or fallback

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
        common = (
            "你是销售培训教练。必须基于输入的客户背景、商机阶段、训练目标、销售SOP知识库生成个性化内容，"
            "不要使用泛泛模板，不要编造未出现的事实。只输出一个合法 JSON 对象，不要 Markdown。\n"
            "固定 JSON 字段：overall_score, summary, scores, good_lines, risk_lines, alternatives, checklist, citations。\n"
            "scores 必须包含 7 项：SOP执行、客户洞察、需求澄清、异议处理、价值表达、推进动作、话术质量；"
            "每项格式为 {\"name\":\"维度\",\"value\":1-5,\"reason\":\"结合本次内容的具体原因\"}。\n"
            "citations 至少引用一条命中的知识库来源，source 使用文档名和版本，reason 写清片段类型、章节/页码和引用原因；"
            "如果知识库为空或明显没有命中，reason 写“依据不足”，不要伪造来源。\n"
            f"训练类型：{session.training_type}\n客户：{session.customer_name} / {session.customer_type}\n"
            f"阶段：{session.stage}\n目标：{session.goal}\n背景：{session.background}\n"
            f"知识库：\n{_knowledge_text(knowledge)}\n"
            f"对话或输入：\n{transcript}\n"
        )
        if session.training_type == "商机推进教练":
            return (
                common
                + "商机推进教练输出要求：\n"
                + "summary 写成当前商机判断，不超过 80 字。\n"
                + "good_lines 写 2 条当前有利条件或可利用抓手。\n"
                + "risk_lines 写 3 条关键风险，必须结合阶段、关键人、阻碍或最近沟通结果。\n"
                + "alternatives 写 3 条不同角度的交涉策略：卡点复述、关键人推进、条件换承诺；每条要能直接照着说或照着做。\n"
                + "checklist 写 4 个待办对象，格式为 {\"title\":\"事项\",\"detail\":\"执行要点\",\"due\":\"1 天内/2 天内/3 天内/5 天内\"}。\n"
            )
        return (
            common
            + "客户情景陪练输出要求：\n"
            + "summary 写成教练总体评价，不超过 80 字。\n"
            + "good_lines 摘录或改写 2 条本轮表现亮点。\n"
            + "risk_lines 指出 2 条具体话术风险。\n"
            + "alternatives 给 2-3 条替代话术，必须可直接用于下一次客户沟通。\n"
            + "checklist 给 3 个下一轮训练动作。\n"
        )

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

    async def _chat(self, messages: list[dict], config: EffectiveLLMConfig, max_tokens: int = 1024) -> str:
        if config.base_url:
            if "anthropic" in config.base_url.lower():
                return await self._chat_anthropic_compatible(messages, config, max_tokens)
            return await self._chat_openai_compatible(messages, config, max_tokens)
        return await self._chat_legacy(messages, config, max_tokens)

    async def _chat_anthropic_compatible(self, messages: list[dict], config: EffectiveLLMConfig, max_tokens: int) -> str:
        base_url = config.base_url.rstrip("/")
        url = base_url if base_url.endswith("/messages") else f"{base_url}/v1/messages"
        system, chat_messages = self._anthropic_messages(messages)
        payload = {
            "model": config.model_id,
            "max_tokens": max_tokens,
            "messages": chat_messages,
        }
        if system:
            payload["system"] = system
        headers = {
            "x-api-key": config.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        body = await self._post_json(url, payload, headers)
        content = body.get("content") or []
        if isinstance(content, str):
            return content
        return "".join(part.get("text", "") for part in content if isinstance(part, dict))

    async def _chat_openai_compatible(self, messages: list[dict], config: EffectiveLLMConfig, max_tokens: int) -> str:
        base_url = config.base_url.rstrip("/")
        url = base_url if base_url.endswith("/chat/completions") else f"{base_url}/chat/completions"
        payload = {"model": config.model_id, "messages": self._openai_messages(messages), "max_tokens": max_tokens}
        headers = {"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"}
        body = await self._post_json(url, payload, headers)
        choices = body.get("choices") or []
        if not choices:
            return ""
        choice = choices[0]
        message = choice.get("message") or {}
        content = _strip_thinking(message.get("content") or choice.get("text") or "")
        if choice.get("finish_reason") == "length":
            logger.warning("LLM 输出达到 max_tokens 上限被截断 (model=%s, max_tokens=%s)", config.model_id, max_tokens)
        return content

    async def _chat_legacy(self, messages: list[dict], config: EffectiveLLMConfig, max_tokens: int) -> str:
        url = f"https://api.minimax.chat/v1/text/chatcompletion_v2?GroupId={config.group_id}"
        payload = {"model": config.model_id, "messages": messages, "tokens_to_generate": max_tokens}
        headers = {"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"}
        body = await self._post_json(url, payload, headers)
        choices = body.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        return message.get("content") or message.get("text") or ""

    def _openai_messages(self, messages: list[dict]) -> list[dict]:
        converted = []
        for index, message in enumerate(messages):
            sender = message.get("sender_type")
            role = "assistant" if sender == "BOT" else "user"
            if sender == "SYSTEM" or (index == 0 and sender == "BOT"):
                role = "system"
            converted.append({"role": role, "content": message.get("text", "")})
        if converted and not any(message["role"] == "user" for message in converted):
            converted.append({"role": "user", "content": "请开始本次训练。"})
        return converted

    def _anthropic_messages(self, messages: list[dict]) -> tuple[str, list[dict]]:
        system_parts = []
        converted = []
        for index, message in enumerate(messages):
            sender = message.get("sender_type")
            text = message.get("text", "")
            if sender == "SYSTEM" or (index == 0 and sender == "BOT"):
                system_parts.append(text)
                continue
            role = "assistant" if sender == "BOT" else "user"
            converted.append({"role": role, "content": text})
        if not converted:
            converted.append({"role": "user", "content": "请开始。"})
        return "\n".join(system_parts), converted

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

    async def _post_json(self, url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        last_error = None
        async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=15.0)) as client:
            for _ in range(2):
                try:
                    response = await client.post(url, json=payload, headers=headers)
                    response.raise_for_status()
                    return response.json()
                except httpx.HTTPError as exc:
                    last_error = exc
        raise last_error or httpx.HTTPError("LLM request failed")

    def _normalize_report(
        self,
        data: dict[str, Any],
        session: TrainingSession,
        knowledge: list[KnowledgeItem],
    ) -> dict[str, Any]:
        fallback = self._mock_report(session, [], knowledge)
        source = knowledge[0].source_name if knowledge else "模拟销售 SOP"
        source_reason = f"用于判断“{session.stage} / {session.goal}”场景下的推荐动作和禁用话术。"

        scores = data.get("scores")
        if not isinstance(scores, list) or len(scores) < 7:
            scores = fallback["scores"]
        else:
            scores = [self._score_item(item, fallback["scores"][index]) for index, item in enumerate(scores[:7])]

        citations = data.get("citations")
        if not isinstance(citations, list) or not citations:
            citations = [{"source": source, "reason": source_reason}]
        else:
            citations = [self._citation_item(item, source, source_reason) for item in citations[:4]]
        knowledge_sources = {item.source_name for item in knowledge}
        if knowledge_sources and not any(item["source"] in knowledge_sources for item in citations):
            citations.insert(0, {"source": source, "reason": source_reason})
        status = self._text(data.get("llm_status"), "mock:normalized")
        if status.startswith("mock:"):
            citations.insert(0, {"source": "LLM 调用状态", "reason": status})

        normalized = {
            "overall_score": self._score_value(data.get("overall_score"), fallback["overall_score"], 100),
            "summary": self._text(data.get("summary"), fallback["summary"]),
            "scores": scores,
            "good_lines": self._text_list(data.get("good_lines"), fallback["good_lines"], 2),
            "risk_lines": self._text_list(data.get("risk_lines"), fallback["risk_lines"], 2),
            "alternatives": self._text_list(data.get("alternatives"), fallback["alternatives"], 3),
            "checklist": self._text_list(data.get("checklist"), fallback["checklist"], 3),
            "citations": citations,
        }
        if session.training_type == "商机推进教练":
            normalized = self._normalize_opportunity_report(normalized, session, knowledge)
        return normalized

    def _normalize_opportunity_report(
        self,
        data: dict[str, Any],
        session: TrainingSession,
        knowledge: list[KnowledgeItem],
    ) -> dict[str, Any]:
        actions = self._text_list(data.get("alternatives"), [], 4)
        checklist = self._text_list(data.get("checklist"), [], 4)
        default_actions = [
                f"把下一步收敛为“{session.goal}”对应的明确节点，不要只说保持沟通。",
                "围绕当前关键阻碍设计一个具体问题，确认客户内部卡点。",
                "补齐关键人参与情况，确认采购、技术和最终决策人的关注点。",
                "把时间、人员、资料或测试条件写成一个明确的跟进动作。",
        ]
        if len(actions) < 4:
            actions.extend(default_actions[len(actions):])
        if len(checklist) < 3:
            checklist = [
                {"title": "确认下一步节点", "detail": actions[0], "due": "1 天内"},
                {"title": "拆解关键阻碍", "detail": actions[1], "due": "2 天内"},
                {"title": "补齐关键人", "detail": actions[2], "due": "3 天内"},
                {"title": "固化跟进动作", "detail": actions[3], "due": "5 天内"},
            ]
        else:
            checklist = [self._todo_item(item, index, actions) for index, item in enumerate(checklist[:4])]
        data["summary"] = self._text(
            data.get("summary"),
            f"{session.customer_name} 当前处于“{session.stage}”阶段，建议优先把下一步推进动作收敛到明确的人、时间和条件。",
        )
        data["alternatives"] = actions[:4]
        data["checklist"] = checklist[:4]
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
        if not isinstance(item, dict):
            return fallback
        return {
            "name": self._text(item.get("name"), fallback["name"]),
            "value": self._score_value(item.get("value"), fallback["value"], 5),
            "reason": self._text(item.get("reason"), fallback["reason"]),
        }

    def _citation_item(self, item: Any, source: str, reason: str) -> dict[str, str]:
        if not isinstance(item, dict):
            return {"source": source, "reason": reason}
        return {
            "source": self._text(item.get("source"), source),
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
        sales_turns = [m for m in messages if m.role == "sales"]
        concern = getattr(session, "customer_concern", "") or "价格"
        difficulty = getattr(session, "customer_difficulty", "") or "标准"
        personality = getattr(session, "customer_personality", "") or "谨慎型"

        if concern == "价格":
            opening = "价格和预算是我现在最关注的点"
        elif concern == "交期":
            opening = "交期能不能保证是我现在最担心的点"
        elif concern == "品质":
            opening = "品质稳定性和返工风险我需要先确认"
        else:
            opening = "售后响应和后续服务我需要先看清楚"

        if difficulty == "高压":
            pressure = "如果没有更明确的降价、成本依据或保障，我很难继续推进。"
        elif difficulty == "刁钻":
            pressure = "你现在的说法还不够具体，我需要看到依据。"
        else:
            pressure = "你可以先把对我们实际有利的部分讲清楚。"

        if personality == "敷衍型":
            pressure = "我时间不多，你直接说重点。"
        elif personality == "专业型":
            pressure = "最好能给到数据、案例或测试条件。"

        if len(sales_turns) <= 1:
            return f"{opening}。{pressure}"
        if len(sales_turns) == 2:
            return f"听起来有点道理，但围绕{concern}我还没被说服。下一步你准备怎么安排？"
        return f"如果要继续推进，请把{concern}相关的条件、时间和负责人说清楚，否则我这边很难排优先级。"

    def _mock_report(
        self,
        session: TrainingSession,
        messages: list[TrainingMessage],
        knowledge: list[KnowledgeItem],
    ) -> dict:
        source = knowledge[0].source_name if knowledge else "模拟销售 SOP"
        return {
            "overall_score": 78,
            "summary": "本轮能回应客户问题，但推进动作还需要更明确，建议把下一步收敛到关键人、时间和测试条件。",
            "scores": [
                {"name": "SOP执行", "value": 4, "reason": "能围绕阶段推进，但缺少明确确认动作。"},
                {"name": "客户洞察", "value": 3, "reason": "识别了价格或推进顾虑，但没有继续追问决策链。"},
                {"name": "需求澄清", "value": 3, "reason": "对客户真实限制了解不够。"},
                {"name": "异议处理", "value": 4, "reason": "能回应异议，但证据还可以更具体。"},
                {"name": "价值表达", "value": 3, "reason": "价值表达偏泛，需要结合成本、稳定性或交付风险。"},
                {"name": "推进动作", "value": 3, "reason": "下一步动作还不够具体。"},
                {"name": "话术质量", "value": 4, "reason": "表达自然，但收口力度不足。"},
            ],
            "good_lines": ["能先承认客户顾虑，再解释价值。"],
            "risk_lines": ["后续保持沟通这类说法太虚，容易让商机继续停滞。"],
            "alternatives": ["建议改成：我们先约技术和采购一起确认测试条件，您看周三下午是否方便？"],
            "checklist": ["确认关键人", "约定下一次沟通时间", "补充测试或成本依据"],
            "citations": [{"source": source, "reason": "用于判断推荐话术和禁用话术。"}],
        }
