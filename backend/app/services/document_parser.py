from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree


MAX_CHARS = 900


@dataclass
class TextPage:
    page: int | None
    text: str


@dataclass
class TextSection:
    title: str
    content: str
    page_start: int | None = None
    page_end: int | None = None


@dataclass
class ParsedChunk:
    title: str
    chunk_type: str
    section_title: str
    content: str
    stage: str
    scenario: str
    page_start: int | None = None
    page_end: int | None = None
    confidence: int = 70
    metadata: dict = field(default_factory=dict)


@dataclass
class ParsedDocument:
    raw_text: str
    chunks: list[ParsedChunk]
    parse_status: str
    parse_summary: str
    structured_data: dict
    error_message: str = ""


PRODUCT_PATTERNS = [
    ("产品参数", r"参数|指标|规格|含量|pH|PH|粘度|固含|外观|色牢度|型号|标准|浓度|离子"),
    ("应用场景", r"适用|应用|用于|场景|织物|染料|客户|行业|棉|涤|印染"),
    ("工艺条件", r"工艺|温度|时间|浴比|pH|PH|流程|后处理|条件|烘干|浸轧"),
    ("使用方法", r"使用|用法|用量|添加|配比|操作|步骤|稀释|搅拌"),
    ("注意事项", r"注意|避免|储存|安全|包装|保质|运输|防潮|密封"),
    ("技术边界", r"不适用|限制|边界|不能|禁用|风险|不得|不建议"),
    ("价值表达", r"优势|特点|稳定|降低|成本|提升|效果|价值|返修|节省|效率"),
    ("常见问题", r"FAQ|Q[:：]|A[:：]|问[:：]|答[:：]|问题|为什么|怎么办"),
]

SOP_PATTERNS = [
    ("推荐话术", r"推荐|话术|建议说|可以说|表达|回应|开口|客户问"),
    ("禁用话术", r"禁用|不要|避免|不能说|不可|禁止|忌|不允许"),
    ("异议处理", r"异议|压价|拒绝|担心|顾虑|反对|竞品|嫌贵|价格高"),
    ("评分标准", r"评分|标准|评价|扣分|分项|验收|考核|满分"),
    ("客户交涉案例", r"案例|客户说|情景|场景|对话|示例|复盘"),
    ("商机推进规范", r"推进|下一步|里程碑|关键人|成交|跟进|停滞|节点"),
    ("流程节点", r"流程|阶段|节点|步骤|SOP|商机|拜访|报价|回款"),
    ("关键动作", r"动作|执行|确认|获取|约|报价|回款|拜访|送样|打样"),
    ("风险提醒", r"风险|警惕|问题|卡点|阻碍|失败|未通过|拖延"),
]

STAGE_PATTERNS = [
    ("了解商机", r"线索|加微信|首次触达|首访|首次拜访|了解商机"),
    ("确认商机", r"确认商机|需求|样品|再次拜访|关键人确认"),
    ("方案论证", r"方案|论证|打样|试样|报告|技术|工艺|测试"),
    ("商务谈判", r"商务|谈判|报价|价格|账期|交付条件"),
    ("销售成交", r"成交|合同|订单|交付|签订"),
    ("回款", r"回款|付款|账期|服务|复购|老客"),
]

SCENARIO_PATTERNS = [
    ("价格异议", r"价格|报价|降价|压价|嫌贵"),
    ("技术交涉", r"技术|工艺|参数|指标|测试|色牢度"),
    ("报告讲解", r"报告|数据|检测|对比"),
    ("试样推进", r"试样|送样|打样|样品"),
    ("商机停滞", r"停滞|拖延|没有回复|不推进"),
    ("回款交涉", r"回款|付款|账期|对账"),
    ("老客维护", r"老客|订单减少|复购|断单"),
    ("条件谈判", r"账期|交付|责任|合同|条件"),
    ("首次触达", r"首次|陌拜|初次|触达|第一次|加微信|开场"),
    ("约到拜访", r"拜访|约见|上门|见面"),
]


def extract_text(filename: str, raw: bytes) -> str:
    return "\n".join(page.text for page in _extract_pages(filename, raw)).strip()


def split_chunks(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    parts = [part.strip() for part in re.split(r"\n\s*\n|\n(?=\S)", normalized) if part.strip()]
    chunks: list[str] = []
    current = ""
    for part in parts:
        if len(part) > max_chars:
            if current:
                chunks.append(current.strip())
                current = ""
            chunks.extend(_split_long_part(part, max_chars))
            continue
        candidate = f"{current}\n{part}".strip() if current else part
        if len(candidate) > max_chars and current:
            chunks.append(current.strip())
            current = part
        else:
            current = candidate
    if current:
        chunks.append(current.strip())
    return chunks or ([text.strip()] if text.strip() else [])


def parse_document(
    filename: str,
    raw: bytes,
    source_type: str,
    default_stage: str = "通用",
    default_scenario: str = "通用",
) -> ParsedDocument:
    pages = _extract_pages(filename, raw)
    raw_text = "\n\n".join(page.text for page in pages if page.text).strip()
    suffix = Path(filename or "").suffix.lower()
    is_pdf = suffix == ".pdf"
    if not raw_text:
        return ParsedDocument(
            raw_text="",
            chunks=[],
            parse_status="empty",
            parse_summary="未抽取到可用正文。",
            structured_data={"source_type": source_type, "sections": 0, "chunk_types": {}},
            error_message="未抽取到可用正文。",
        )
    if is_pdf and len(re.sub(r"\s+", "", raw_text)) < 80:
        return ParsedDocument(
            raw_text=raw_text,
            chunks=[],
            parse_status="quality_low",
            parse_summary="PDF 文本抽取质量不足，疑似扫描件或图片型 PDF。",
            structured_data={"source_type": source_type, "sections": 0, "chunk_types": {}},
            error_message="PDF 文本抽取质量不足，暂不进入 AI 引用。",
        )

    doc_kind = _document_kind(source_type, raw_text)
    sections = _build_sections(pages)
    chunks = _sections_to_chunks(sections, doc_kind, default_stage, default_scenario)
    chunks = _validate_chunks(chunks)
    status = "parsed" if chunks else "empty"
    counts = _type_counts(chunks)
    summary = f"识别 {len(sections)} 个结构段落，生成 {len(chunks)} 个可引用片段。"
    if not chunks:
        summary = "未生成可引用片段，建议检查文件正文或重新上传更清晰版本。"
    return ParsedDocument(
        raw_text=raw_text,
        chunks=chunks,
        parse_status=status,
        parse_summary=summary,
        structured_data={
            "source_type": source_type,
            "document_kind": doc_kind,
            "sections": len(sections),
            "chunk_types": counts,
            "filename": filename,
        },
    )


def _extract_pages(filename: str, raw: bytes) -> list[TextPage]:
    suffix = Path(filename or "").suffix.lower()
    if suffix == ".docx":
        return [TextPage(None, _extract_docx(raw))]
    if suffix == ".pdf":
        return _extract_pdf_pages(raw)
    return [TextPage(None, _decode_text(raw))]


def _build_sections(pages: list[TextPage]) -> list[TextSection]:
    sections: list[TextSection] = []
    current_title = "正文"
    current_lines: list[str] = []
    page_start: int | None = None
    page_end: int | None = None

    def flush():
        nonlocal current_lines, page_start, page_end
        content = "\n".join(current_lines).strip()
        if content:
            sections.append(TextSection(current_title, content, page_start, page_end))
        current_lines = []
        page_start = None
        page_end = None

    for page in pages:
        for raw_line in page.text.splitlines():
            line = _normalize_line(raw_line)
            if not line:
                continue
            if _looks_like_heading(line) and current_lines:
                flush()
                current_title = line[:120]
            elif _looks_like_heading(line):
                current_title = line[:120]
            else:
                current_lines.append(line)
                page_start = page.page if page_start is None else page_start
                page_end = page.page or page_end
        if current_lines and page.page:
            page_end = page.page
    flush()
    if len(sections) <= 1:
        return _paragraph_sections("\n".join(page.text for page in pages))
    return sections


def _paragraph_sections(text: str) -> list[TextSection]:
    chunks = split_chunks(text, MAX_CHARS)
    return [TextSection(f"段落 {index}", chunk) for index, chunk in enumerate(chunks, start=1)]


def _sections_to_chunks(
    sections: list[TextSection],
    doc_kind: str,
    default_stage: str,
    default_scenario: str,
) -> list[ParsedChunk]:
    chunks: list[ParsedChunk] = []
    for section in sections:
        parts = split_chunks(section.content, MAX_CHARS)
        for part_index, part in enumerate(parts, start=1):
            text_for_classify = f"{section.title}\n{part}"
            chunk_type, type_score = _classify_type(text_for_classify, doc_kind)
            stage, stage_score = _infer_value(text_for_classify, STAGE_PATTERNS, default_stage)
            scenario, scenario_score = _infer_value(text_for_classify, SCENARIO_PATTERNS, default_scenario)
            title = _chunk_title(section.title, chunk_type, part_index, len(parts))
            confidence = min(95, 55 + type_score + stage_score + scenario_score + (5 if section.title != "正文" else 0))
            chunks.append(
                ParsedChunk(
                    title=title,
                    chunk_type=chunk_type,
                    section_title=section.title,
                    content=part,
                    stage=stage,
                    scenario=scenario,
                    page_start=section.page_start,
                    page_end=section.page_end,
                    confidence=max(45, confidence),
                    metadata={"document_kind": doc_kind, "part": part_index, "parts": len(parts)},
                )
            )
    return chunks


def _classify_type(text: str, doc_kind: str) -> tuple[str, int]:
    patterns = PRODUCT_PATTERNS if doc_kind == "product" else SOP_PATTERNS
    best_type = "知识片段"
    best_score = 0
    for chunk_type, pattern in patterns:
        score = len(re.findall(pattern, text, flags=re.IGNORECASE))
        if score > best_score:
            best_type = chunk_type
            best_score = score
    if best_score:
        return best_type, min(20, 10 + best_score * 3)
    return ("应用场景" if doc_kind == "product" else "关键动作", 8)


def _infer_value(text: str, patterns: list[tuple[str, str]], fallback: str) -> tuple[str, int]:
    for value, pattern in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return value, 8
    return fallback or "通用", 0


def _validate_chunks(chunks: list[ParsedChunk]) -> list[ParsedChunk]:
    valid: list[ParsedChunk] = []
    seen: set[str] = set()
    for chunk in chunks:
        content = " ".join(chunk.content.split())
        if len(content) < 12:
            continue
        fingerprint = re.sub(r"\W+", "", content.lower())[:180]
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        chunk.content = content
        valid.append(chunk)
    return valid


def _document_kind(source_type: str, text: str) -> str:
    if re.search(r"产品说明书|产品|manual", source_type or "", flags=re.IGNORECASE):
        return "product"
    if source_type:
        return "sop"
    marker = (text or "")[:600]
    if re.search(r"产品|说明书|参数|规格|工艺|product|manual", marker, flags=re.IGNORECASE):
        return "product"
    return "sop"


def _chunk_title(section_title: str, chunk_type: str, part_index: int, total_parts: int) -> str:
    base = section_title if section_title and section_title != "正文" else chunk_type
    suffix = f" {part_index}" if total_parts > 1 else ""
    return f"{base}{suffix}"[:120]


def _looks_like_heading(line: str) -> bool:
    if len(line) > 42:
        return False
    if re.match(r"^(\d+(\.\d+)*|[一二三四五六七八九十]+[、.．])\s*.+", line):
        return True
    if re.search(r"(流程|阶段|节点|话术|评分|参数|规格|用途|工艺|工艺条件|使用方法|应用场景|技术边界|价值表达|注意事项|FAQ|常见问题)$", line):
        return True
    if line.endswith(("：", ":")) and len(line) <= 28:
        return True
    return False


def _normalize_line(line: str) -> str:
    return re.sub(r"\s+", " ", line.replace("\u3000", " ")).strip()


def _type_counts(chunks: list[ParsedChunk]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for chunk in chunks:
        counts[chunk.chunk_type] = counts.get(chunk.chunk_type, 0) + 1
    return counts


def _split_long_part(part: str, max_chars: int) -> list[str]:
    return [part[i : i + max_chars].strip() for i in range(0, len(part), max_chars) if part[i : i + max_chars].strip()]


def _decode_text(raw: bytes) -> str:
    for encoding in ("utf-8", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", errors="ignore")


def _extract_docx(raw: bytes) -> str:
    try:
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            xml = archive.read("word/document.xml")
    except Exception:
        return _decode_text(raw)
    root = ElementTree.fromstring(xml)
    paragraphs: list[str] = []
    for paragraph in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
        texts = [
            node.text or ""
            for node in paragraph.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t")
        ]
        line = "".join(texts).strip()
        if line:
            paragraphs.append(line)
    return "\n".join(paragraphs)


def _extract_pdf_pages(raw: bytes) -> list[TextPage]:
    try:
        from pypdf import PdfReader
    except Exception:
        return [TextPage(None, _decode_text(raw))]
    try:
        reader = PdfReader(BytesIO(raw))
        return [
            TextPage(index, (page.extract_text() or "").strip())
            for index, page in enumerate(reader.pages, start=1)
        ]
    except Exception:
        return [TextPage(None, _decode_text(raw))]
