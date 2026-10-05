import json
import logging
import re
import time
from typing import Any, AsyncGenerator

import httpx

from app.models import KnowledgeItem, TrainingMessage, TrainingSession
from app.services.llm_config import EffectiveLLMConfig, get_effective_llm_config

logger = logging.getLogger(__name__)

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
            "2. 追问风格参考（口语、具体，照着这种味道说）：\n"
            "   - [tech]你们湿擦跟固色剂能不能同浴？\n"
            "   - [buyer]我们水硬度高、夏天水温五六十度，用哪一款？\n"
            "   - [buyer]大货会不会比小样差半级？\n"
            "   - [tech]日标还是国标测的？标准都不一样\n"
            "   - [tech]涂料/化纤是不是根本提不上来？\n"
            "   - [tech]HT-790 真不含双酚？残留多少？\n"
            "   - [boss]你先给个诚意价。\n"
            "3. 业务员若不问清水质、水温、使用工艺（浸轧/浸渍/喷淋）、布种、测试标准，就不要给完整信息：可以不耐烦、反问、或只给部分条件。\n"
            "4. 不要编造资料里没有的产品事实；资料里没有的信息就说「不清楚/要问技术」。\n"
            "5. 可以压价、施压，但必须挂在具体产品/工艺点上（某型号效果、某工艺风险、某测试标准），不要空泛说「太贵了」。\n"
            "6. 不要向业务员背诵资料原文，不要报来源、不要念参数表。\n\n"
            "# 客户画像\n"
            f"{_customer_profile_text(session)}\n"
            f"客户公司：{session.customer_name} / {session.customer_type}\n"
            f"训练类型：{session.training_type}\n商机阶段：{session.stage}\n训练目标：{session.goal}\n"
            f"背景：{session.background}\n\n"
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
        cards_text = _product_cards_text(session, knowledge)
        cards_block = f"\n产品卡：\n{cards_text}" if cards_text else ""
        prompt = (
            "你是销售话术教练。请根据当前训练上下文，给业务员生成一条可参考的下一句回复。"
            "要求：只输出一句自然口语化回复，不要解释，不要编号；必须回应客户刚才的问题，并推动一个明确下一步。"
            "不要承诺无法确认的数据，不要直接降价，不要说空泛的保持沟通。控制在 80 字以内。\n"
            f"客户最后一句：{last_customer}\n"
            f"训练类型：{session.training_type}\n阶段：{session.stage}\n目标：{session.goal}\n"
            f"客户：{session.customer_name} / {session.customer_type}\n背景：{session.background}\n"
            f"知识库：\n{_knowledge_text(knowledge)}\n"
            f"{cards_block}\n"
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
        cards_text = _product_cards_text(session, knowledge)
        cards_block = f"\n产品卡（选型/边界/价值参考）：\n{cards_text}\n" if cards_text else ""

        common = (
            "你是纺织助剂行业销售培训教练（宏昊化工场景：固色剂/湿摩擦提升剂/硅油/前后整理助剂）。"
            "必须基于输入的客户背景、商机阶段、训练目标、产品与工艺知识库生成个性化内容，"
            "不要使用泛泛模板，不要编造未出现的事实。只输出一个合法 JSON 对象，不要 Markdown。\n"
            "固定 JSON 字段：overall_score, summary, scores, good_lines, risk_lines, alternatives, checklist, citations。\n"
            "scores 必须包含 7 项：工艺探询、产品选型、技术边界、异议处理、故障归因、价值合规、推进动作；"
            "每项格式为 {\"name\":\"维度\",\"value\":1-5,\"reason\":\"结合本次内容的具体原因\"}。\n"
            "citations 至少引用一条命中的知识库来源，source 使用文档名和版本，reason 写清片段类型、章节/页码和引用原因；"
            "如果知识库为空或明显没有命中，reason 写“依据不足”，不要伪造来源。\n"
            "若对话中出现技术/老板入场（客户消息带 [tech]/[boss] 等角色标签），"
            "客户洞察与异议处理可参照多角色表现：技术追问是否接住、老板拍板/底线是否回应。\n\n"
            "## 评分标准（必须严格遵循）\n"
            f"{scoring_criteria}\n\n"
            "## 评分计算规则\n"
            "1. overall_score = (工艺探询×0.15 + 产品选型×0.15 + 技术边界×0.15 + 异议处理×0.15 + 故障归因×0.10 + 价值合规×0.15 + 推进动作×0.15) × 20\n"
            "2. 每个维度必须基于对话中的具体表现评分，不能使用固定分数\n"
            "3. 如果对话轮次少于3轮，整体评分不得超过70分\n"
            "4. 若业务员未问清水质、水温、使用工艺（浸轧/浸渍/喷淋）中的任意两项，工艺探询不得超过2分\n"
            "5. 若推荐型号明显不匹配客户已知条件（如水质差/水温高却只推 833 而非高稳 831B/868），产品选型不得超过2分\n"
            "6. 若对涂料/化纤难提升、大货小样差异、同浴沉淀风险等技术边界有瞎承诺，技术边界不得超过2分\n"
            "7. 如果没有明确的下一步动作（试样、小样条件、工程师介入、明确人/时间/条件），推进动作不得超过2分\n"
            "8. 如果没有引用知识库内容，价值合规或产品选型不得满分\n\n"
            f"训练类型：{session.training_type}\n客户：{session.customer_name} / {session.customer_type}\n"
            f"阶段：{session.stage}\n目标：{session.goal}\n背景：{session.background}\n"
            f"知识库：\n{_knowledge_text(knowledge)}\n"
            f"{cards_block}"
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
            + "good_lines 摘录或改写 2 条本轮表现亮点，尽量点出具体型号、工艺参数、认证或案例。\n"
            + "risk_lines 指出 2 条具体话术风险，结合型号错配、边界瞎承诺、水质/工艺未问清等。\n"
            + "alternatives 给 2-3 条替代话术，必须可直接用于下一次客户沟通，含具体型号、工艺条件、测试标准或认证价值。\n"
            + "checklist 给 3 个下一轮训练动作，写清可执行条件（如补问水质水温、约工程师定小样条件、准备测试报告）。\n"
        )

    def _build_scoring_criteria(
        self,
        session: TrainingSession,
        sales_turns: int,
        avg_sales_length: float,
    ) -> str:
        """构建纺织助剂行业评分标准，基于对话统计和训练目标"""
        criteria = []

        # 工艺探询维度
        criteria.append("### 工艺探询（权重15%）——望闻问切四要素：水质、水温、使用工艺（浸轧/浸渍/喷淋）、布种；测试标准（日标/国标）为加分探询项")
        criteria.append("- 5分：系统问清望闻问切四要素（水质/水温/工艺/布种），并确认测试标准后收敛推荐")
        criteria.append("- 4分：问清望闻问切中三项，但遗漏布种或测试标准")
        criteria.append("- 3分：问了部分条件，但水质/水温/工艺中仍有两项以上未确认")
        criteria.append("- 2分：几乎只报型号不问条件，或问了但不跟进确认")
        criteria.append("- 1分：完全未做工艺条件探询就直接推产品")

        # 产品选型维度
        criteria.append("\n### 产品选型（权重15%）——推荐型号是否匹配客户条件（如水质差/水温高应推高稳 831B/868 而非只推 833）")
        criteria.append("- 5分：型号与水质/水温/布种/工艺高度匹配，并说明为何选这款而非竞品款")
        criteria.append("- 4分：选型基本匹配，但未说明取舍理由或备选方案")
        criteria.append("- 3分：推了通用款，未针对已知条件（硬水/高温/涂料布）做差异化")
        criteria.append("- 2分：型号与已知条件明显不匹配（如高温高硬仍只推 833）")
        criteria.append("- 1分：乱推型号，或推了与场景无关的产品")

        # 技术边界维度
        criteria.append("\n### 技术边界（权重15%）——是否诚实说明局限（涂料/化纤难提升、大货小样差异、同浴沉淀风险），不瞎承诺")
        criteria.append("- 5分：主动说明技术边界与风险，并给出可控条件（分浴、补加、测试口径）")
        criteria.append("- 4分：说明了主要边界，但个别风险未点透")
        criteria.append("- 3分：提到局限但含糊，或只在被追问后才承认")
        criteria.append("- 2分：对涂料/化纤提升、大货小样差异、同浴等问题有夸大或含糊承诺")
        criteria.append("- 1分：满口保证绝无问题，明显瞎承诺")

        # 异议处理维度
        criteria.append("\n### 异议处理（权重15%）——能否用参数/案例/测试标准回应，而非空话")
        criteria.append("- 5分：用具体参数、测试标准（日标/国标/湿摩擦级数）、案例或数据回应异议")
        criteria.append("- 4分：有依据地回应，但证据不够贴合客户场景")
        criteria.append("- 3分：尝试回应，但以安抚话术为主，缺硬证据")
        criteria.append("- 2分：回避异议或空泛保证「没问题」")
        criteria.append("- 1分：完全没有处理客户异议")

        # 故障归因维度
        criteria.append("\n### 故障归因（权重10%）——出现客诉/斑/色变/气味时是否先归因（水质、残留、同浴、温度）再认赔")
        criteria.append("- 5分：先按水质/残留/同浴/温度/工艺窗口系统归因，再定责与整改方案")
        criteria.append("- 4分：做了归因但漏掉 1 个关键变量（如未查水硬度或残留）")
        criteria.append("- 3分：提到可能原因但未排查路径，过早给补偿口径")
        criteria.append("- 2分：跳过归因直接道歉认赔，或甩锅客户")
        criteria.append("- 1分：完全没有故障分析意识")

        # 价值合规维度
        criteria.append("\n### 价值合规（权重15%）——是否表达认证（bluesign/GOTS/OEKO-TEX/ZDHC）、省水省时、稳定性价值，而不是只谈降价")
        criteria.append("- 5分：结合认证、省水省时、批次稳定/返工风险下降等价值，并与客户痛点挂钩")
        criteria.append("- 4分：表达了合规或效率价值，但与客户账算得不够细")
        criteria.append("- 3分：价值表达偏泛，或只谈一点价格")
        criteria.append("- 2分：几乎只谈降价/折扣，无合规与效率价值")
        criteria.append("- 1分：完全没有价值表达，或违反合规口径乱承诺证书")

        # 推进动作维度
        criteria.append("\n### 推进动作（权重15%）——是否推进到试样、小样条件、工程师介入、明确下一步人/时间/条件")
        criteria.append("- 5分：推进到试样/小样条件确认，明确工程师介入与下一步人、时间、条件")
        criteria.append("- 4分：有明确下一步，但缺少责任人或具体小样条件")
        criteria.append("- 3分：提出下一步但不够具体（如「再联系」）")
        criteria.append("- 2分：下一步动作模糊或不可执行")
        criteria.append("- 1分：完全没有推进动作")

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
        
        # 权重配置（纺织助剂行业七维）
        weights = {
            "工艺探询": 0.15,
            "产品选型": 0.15,
            "技术边界": 0.15,
            "异议处理": 0.15,
            "故障归因": 0.10,
            "价值合规": 0.15,
            "推进动作": 0.15,
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

        # 对话轮次不足时整体封顶（与 prompt 硬约束一致）
        try:
            sales_turns = len([m for m in (getattr(session, "messages", None) or []) if getattr(m, "role", "") == "sales"])
        except Exception:
            sales_turns = 3
        if sales_turns < 3:
            overall_score = min(overall_score, 70)

        return max(0, min(100, overall_score))

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
        # 白名单校验维度名，防止 LLM 回传旧维（SOP执行/价值表达等）混入
        allowed = {
            "工艺探询",
            "产品选型",
            "技术边界",
            "异议处理",
            "故障归因",
            "价值合规",
            "推进动作",
        }
        name = self._text(item.get("name"), "")
        if name not in allowed:
            name = fallback.get("name", "工艺探询")
        return {
            "name": name,
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
            return f"[buyer]{opening}。{pressure}"
        if len(sales_turns) == 2:
            return f"[buyer]听起来有点道理，但围绕{concern}我还没被说服。下一步你准备怎么安排？"
        return f"[buyer]如果要继续推进，请把{concern}相关的条件、时间和负责人说清楚，否则我这边很难排优先级。"

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
