import json
import logging
import time
from typing import Any, AsyncGenerator

import httpx

from app.models import KnowledgeItem, TrainingMessage, TrainingSession
from app.services.llm_config import EffectiveLLMConfig, get_effective_llm_config

logger = logging.getLogger(__name__)


class _DictObj:
    """将 dict 包装为支持属性访问的对象，用于 SSE 快照。"""

    def __init__(self, d: dict):
        self._d = d

    def __getattr__(self, name: str):
        try:
            return self._d[name]
        except KeyError:
            raise AttributeError(name)


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
            "# 角色\n"
            "你是客户，不是业务员。你正在和一家供应商的业务员对话。\n"
            "你只能以客户身份说话，绝对不要替业务员回答、不要帮业务员出主意、不要说业务员会说的话。\n"
            "不要轻易被说服，要围绕客户背景、商机阶段和训练目标持续追问、施压、提条件。\n"
            "每次回复控制在 80 字以内，像真实客户自然说话。不要输出编号、不要分点、不要解释。\n\n"
            "# 客户画像\n"
            f"{_customer_profile_text(session)}\n"
            f"客户公司：{session.customer_name} / {session.customer_type}\n"
            f"训练类型：{session.training_type}\n商机阶段：{session.stage}\n训练目标：{session.goal}\n"
            f"背景：{session.background}\n\n"
            "# 知识库（仅供你了解产品信息，不要在回复中引用来源）\n"
            f"{_knowledge_text(knowledge)}"
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

        prompt = (
            "# 角色\n"
            "你是客户，不是业务员。你正在和一家供应商的业务员对话。\n"
            "你只能以客户身份说话，绝对不要替业务员回答、不要帮业务员出主意、不要说业务员会说的话。\n"
            "不要轻易被说服，要围绕客户背景、商机阶段和训练目标持续追问、施压、提条件。\n"
            "每次回复控制在 80 字以内，像真实客户自然说话。不要输出编号、不要分点、不要解释。\n\n"
            "# 客户画像\n"
            f"{_customer_profile_text(session)}\n"
            f"客户公司：{session.customer_name} / {session.customer_type}\n"
            f"训练类型：{session.training_type}\n商机阶段：{session.stage}\n训练目标：{session.goal}\n"
            f"背景：{session.background}\n\n"
            "# 知识库（仅供你了解产品信息，不要在回复中引用来源）\n"
            f"{_knowledge_text(knowledge)}"
        )
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
        if not self._configured(config):
            report = self._mock_report(session, messages, knowledge)
            report["llm_status"] = "mock:not_configured"
            return self._normalize_report(report, session, knowledge)

        prompt = self._report_prompt(session, messages, knowledge)
        try:
            data = await self._chat([{"sender_type": "USER", "text": prompt}], config, max_tokens=2048)
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
        
        # 分析对话统计数据
        sales_messages = [m for m in messages if m.role == "sales"]
        customer_messages = [m for m in messages if m.role == "customer"]
        sales_turns = len(sales_messages)
        avg_sales_length = sum(len(m.content) for m in sales_messages) / max(sales_turns, 1)
        
        # 构建详细的评分标准
        scoring_criteria = self._build_scoring_criteria(session, sales_turns, avg_sales_length)
        
        common = (
            "你是销售培训教练。必须基于输入的客户背景、商机阶段、训练目标、销售SOP知识库生成个性化内容，"
            "不要使用泛泛模板，不要编造未出现的事实。只输出一个合法 JSON 对象，不要 Markdown。\n"
            "固定 JSON 字段：overall_score, summary, scores, good_lines, risk_lines, alternatives, checklist, citations。\n"
            "scores 必须包含 7 项：SOP执行、客户洞察、需求澄清、异议处理、价值表达、推进动作、话术质量；"
            "每项格式为 {\"name\":\"维度\",\"value\":1-5,\"reason\":\"结合本次内容的具体原因\"}。\n"
            "citations 至少引用一条命中的知识库来源，source 使用文档名和版本，reason 写清片段类型、章节/页码和引用原因；"
            "如果知识库为空或明显没有命中，reason 写“依据不足”，不要伪造来源。\n\n"
            "## 评分标准（必须严格遵循）\n"
            f"{scoring_criteria}\n\n"
            "## 评分计算规则\n"
            "1. overall_score = (SOP执行×0.15 + 客户洞察×0.15 + 需求澄清×0.15 + 异议处理×0.15 + 价值表达×0.15 + 推进动作×0.15 + 话术质量×0.10) × 20\n"
            "2. 每个维度必须基于对话中的具体表现评分，不能使用固定分数\n"
            "3. 如果对话轮次少于3轮，整体评分不得超过70分\n"
            "4. 如果没有明确的下一步动作，推进动作维度不得超过2分\n"
            "5. 如果没有引用知识库内容，SOP执行维度不得超过3分\n\n"
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

    def _build_scoring_criteria(
        self,
        session: TrainingSession,
        sales_turns: int,
        avg_sales_length: float,
    ) -> str:
        """构建详细的评分标准，基于对话统计和训练目标"""
        criteria = []
        
        # SOP执行维度
        criteria.append("### SOP执行（权重15%）")
        criteria.append("- 5分：严格遵循销售流程，每一步都有明确的确认动作")
        criteria.append("- 4分：基本遵循流程，但缺少1-2个确认动作")
        criteria.append("- 3分：部分遵循流程，但有多处遗漏")
        criteria.append("- 2分：流程执行混乱，缺少关键步骤")
        criteria.append("- 1分：完全没有遵循销售流程")
        
        # 客户洞察维度
        criteria.append("\n### 客户洞察（权重15%）")
        criteria.append("- 5分：准确识别客户真实需求、决策链和关键顾虑")
        criteria.append("- 4分：识别了主要需求，但对决策链了解不足")
        criteria.append("- 3分：识别了表面需求，但没有深入挖掘")
        criteria.append("- 2分：对客户需求理解肤浅")
        criteria.append("- 1分：完全没有关注客户需求")
        
        # 需求澄清维度
        criteria.append("\n### 需求澄清（权重15%）")
        criteria.append("- 5分：通过有效提问澄清了客户的真实需求和限制条件")
        criteria.append("- 4分：澄清了主要需求，但遗漏了部分关键信息")
        criteria.append("- 3分：进行了基本澄清，但深度不够")
        criteria.append("- 2分：澄清问题很少或无效")
        criteria.append("- 1分：完全没有进行需求澄清")
        
        # 异议处理维度
        criteria.append("\n### 异议处理（权重15%）")
        criteria.append("- 5分：有效回应客户异议，提供具体证据和解决方案")
        criteria.append("- 4分：回应了异议，但证据不够充分")
        criteria.append("- 3分：尝试回应异议，但缺乏说服力")
        criteria.append("- 2分：回避或忽视客户异议")
        criteria.append("- 1分：完全没有处理客户异议")
        
        # 价值表达维度
        criteria.append("\n### 价值表达（权重15%）")
        criteria.append("- 5分：清晰表达产品/服务价值，与客户需求紧密结合")
        criteria.append("- 4分：表达了价值，但与客户需求关联不够紧密")
        criteria.append("- 3分：价值表达泛泛，缺乏针对性")
        criteria.append("- 2分：价值表达模糊或自相矛盾")
        criteria.append("- 1分：完全没有表达价值")
        
        # 推进动作维度
        criteria.append("\n### 推进动作（权重15%）")
        criteria.append("- 5分：明确下一步动作，包括人员、时间、条件和验证方式")
        criteria.append("- 4分：有下一步动作，但缺少1-2个关键要素")
        criteria.append("- 3分：提出了下一步，但不够具体")
        criteria.append("- 2分：下一步动作模糊或不可执行")
        criteria.append("- 1分：完全没有推进动作")
        
        # 话术质量维度
        criteria.append("\n### 话术质量（权重10%）")
        criteria.append("- 5分：表达自然、专业，有说服力，符合销售场景")
        criteria.append("- 4分：表达清晰，但缺乏感染力")
        criteria.append("- 3分：表达基本通顺，但不够专业")
        criteria.append("- 2分：表达生硬或存在明显问题")
        criteria.append("- 1分：表达混乱或不恰当")
        
        # 添加对话统计信息
        criteria.append(f"\n## 本次对话统计")
        criteria.append(f"- 业务员轮次：{sales_turns}轮")
        criteria.append(f"- 平均回复长度：{avg_sales_length:.0f}字")
        criteria.append(f"- 训练目标：{session.goal}")
        criteria.append(f"- 商机阶段：{session.stage}")
        
        # 根据对话轮次调整评分要求
        if sales_turns < 3:
            criteria.append("\n## 特殊评分要求")
            criteria.append("- 对话轮次不足3轮，整体评分不得超过70分")
            criteria.append("- 需要在summary中说明对话轮次不足的影响")
        
        return "\n".join(criteria)

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

    async def _chat_stream(
        self, messages: list[dict], config: EffectiveLLMConfig, max_tokens: int = 1024
    ) -> AsyncGenerator[str, None]:
        if config.base_url:
            if "anthropic" in config.base_url.lower():
                async for chunk in self._chat_stream_anthropic_compatible(messages, config, max_tokens):
                    yield chunk
            else:
                async for chunk in self._chat_stream_openai_compatible(messages, config, max_tokens):
                    yield chunk
        else:
            result = await self._chat_legacy(messages, config, max_tokens)
            if result:
                yield result

    async def _chat_stream_openai_compatible(
        self, messages: list[dict], config: EffectiveLLMConfig, max_tokens: int
    ) -> AsyncGenerator[str, None]:
        base_url = config.base_url.rstrip("/")
        url = base_url if base_url.endswith("/chat/completions") else f"{base_url}/chat/completions"
        payload = {
            "model": config.model_id,
            "messages": self._openai_messages(messages),
            "max_tokens": max_tokens,
            "stream": True,
        }
        headers = {"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=15.0)) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                        choices = obj.get("choices") or []
                        if choices:
                            delta = choices[0].get("delta") or {}
                            content = delta.get("content")
                            if content:
                                yield content
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

    async def _chat_stream_anthropic_compatible(
        self, messages: list[dict], config: EffectiveLLMConfig, max_tokens: int
    ) -> AsyncGenerator[str, None]:
        base_url = config.base_url.rstrip("/")
        url = base_url if base_url.endswith("/messages") else f"{base_url}/v1/messages"
        system, chat_messages = self._anthropic_messages(messages)
        payload = {
            "model": config.model_id,
            "max_tokens": max_tokens,
            "messages": chat_messages,
            "stream": True,
        }
        if system:
            payload["system"] = system
        headers = {
            "x-api-key": config.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=15.0)) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    try:
                        obj = json.loads(line[6:])
                        if obj.get("type") == "content_block_delta":
                            delta = obj.get("delta") or {}
                            text = delta.get("text")
                            if text:
                                yield text
                    except (json.JSONDecodeError, KeyError):
                        continue

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

        # 重新计算overall_score，确保符合权重规则
        overall_score = self._calculate_overall_score(scores, session)
        
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
            "overall_score": overall_score,
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

    def _calculate_overall_score(
        self,
        scores: list[dict[str, Any]],
        session: TrainingSession,
    ) -> int:
        """根据权重规则计算总分"""
        if not scores or len(scores) < 7:
            return 70
        
        # 权重配置
        weights = {
            "SOP执行": 0.15,
            "客户洞察": 0.15,
            "需求澄清": 0.15,
            "异议处理": 0.15,
            "价值表达": 0.15,
            "推进动作": 0.15,
            "话术质量": 0.10,
        }
        
        weighted_sum = 0
        total_weight = 0
        
        for score_item in scores:
            name = score_item.get("name", "")
            value = score_item.get("value", 3)
            weight = weights.get(name, 0.15)
            weighted_sum += value * weight
            total_weight += weight
        
        # 计算加权平均分（满分5分）
        if total_weight > 0:
            avg_score = weighted_sum / total_weight
        else:
            avg_score = 3.0
        
        # 转换为100分制
        overall_score = int(avg_score * 20)
        
        # 限制分数范围
        overall_score = max(60, min(100, overall_score))
        
        return overall_score

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
        
        # 分析对话内容
        sales_messages = [m for m in messages if m.role == "sales"]
        customer_messages = [m for m in messages if m.role == "customer"]
        sales_turns = len(sales_messages)
        
        # 提取关键信息
        has_next_step = False
        has_value_expression = False
        has_objection_handling = False
        has_clarification = False
        
        # 分析销售人员的表现
        for msg in sales_messages:
            content = msg.content.lower()
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
        
        # 限制分数范围
        overall_score = min(100, max(60, base_score))
        
        # 根据表现生成个性化评分
        scores = []
        
        # SOP执行评分
        sop_score = 3
        sop_reason = "基本遵循销售流程，但缺少明确确认动作。"
        if sales_turns >= 3:
            sop_score = 4
            sop_reason = "能围绕阶段推进，但缺少明确确认动作。"
        if has_next_step:
            sop_score = 5
            sop_reason = "严格遵循销售流程，每一步都有明确的确认动作。"
        scores.append({"name": "SOP执行", "value": sop_score, "reason": sop_reason})
        
        # 客户洞察评分
        insight_score = 3
        insight_reason = "识别了价格或推进顾虑，但没有继续追问决策链。"
        if has_clarification:
            insight_score = 4
            insight_reason = "识别了主要需求，但对决策链了解不足。"
        scores.append({"name": "客户洞察", "value": insight_score, "reason": insight_reason})
        
        # 需求澄清评分
        clarify_score = 3
        clarify_reason = "对客户真实限制了解不够。"
        if has_clarification:
            clarify_score = 4
            clarify_reason = "澄清了主要需求，但遗漏了部分关键信息。"
        scores.append({"name": "需求澄清", "value": clarify_score, "reason": clarify_reason})
        
        # 异议处理评分
        objection_score = 3
        objection_reason = "尝试回应异议，但缺乏说服力。"
        if has_objection_handling:
            objection_score = 4
            objection_reason = "回应了异议，但证据不够充分。"
        scores.append({"name": "异议处理", "value": objection_score, "reason": objection_reason})
        
        # 价值表达评分
        value_score = 3
        value_reason = "价值表达偏泛，需要结合成本、稳定性或交付风险。"
        if has_value_expression:
            value_score = 4
            value_reason = "表达了价值，但与客户需求关联不够紧密。"
        scores.append({"name": "价值表达", "value": value_score, "reason": value_reason})
        
        # 推进动作评分
        action_score = 3
        action_reason = "下一步动作还不够具体。"
        if has_next_step:
            action_score = 4
            action_reason = "有下一步动作，但缺少1-2个关键要素。"
        scores.append({"name": "推进动作", "value": action_score, "reason": action_reason})
        
        # 话术质量评分
        speech_score = 3
        speech_reason = "表达基本通顺，但不够专业。"
        if sales_turns >= 3:
            speech_score = 4
            speech_reason = "表达清晰，但缺乏感染力。"
        scores.append({"name": "话术质量", "value": speech_score, "reason": speech_reason})
        
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
