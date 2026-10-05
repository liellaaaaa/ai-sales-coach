from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

# 产品卡内容提炼自 kb/ 研发培训资料，字段固定：
# code / title / positioning / process / params / boundaries / faults / certs / cases
# 值为字符串或短字符串列表，便于注入 LLM prompt。

PRODUCT_CARDS: list[dict] = [
    {
        "code": "HT-766",
        "title": "同浴固色剂 HT-766",
        "positioning": "中性酸性固色剂，染固同浴不需调酸可直接加入；主打染护同绿、省水省时。",
        "process": [
            "染固同浴一浴法：染料升温至80℃加入HT-766及匀染剂，继续升温98℃染色固色30～60分钟后排水",
            "染色后不排液：98℃运行完降温至80℃加固色剂，运行10～20分钟后排液",
        ],
        "params": [
            "pH约8～10弱碱，8左右不会腐蚀客户管道",
            "工厂大试：泡水牢度4级、水洗牢度3级以上",
            "搭配工艺可使残留小于50，符合多数环保要求",
        ],
        "boundaries": [
            "敏感色（尤其灰色）固色后色变风险偏大，需在褪色后/褪色时排列并修正色光",
            "同浴残液深浅与匀染剂搭配关系大，建议与匀染剂TY1搭配",
            "与常规固色剂牢度有小幅差异，需搭配工艺保护",
        ],
        "faults": ["灰色等敏感色色变偏大", "同浴固色后染色残液偏深"],
        "certs": ["对照蓝标/OEKO-TEX法规开发，低碳无酚胺方向", "残留可控在50以下，符合多数环保要求"],
        "cases": [
            "无缝内衣染固同浴后排液：节省约两缸水，色后水底4级",
            "染色后不排液工艺：后段加四排，牢固与手感同时达标",
            "对比市售60多款固色剂，牢固度与性价比有优势；每吨布可省数百元",
        ],
    },
    {
        "code": "HT-790",
        "title": "无酚固色剂 HT-790",
        "positioning": "明星无酚固色剂，完全不含双酚、苯酚、对苯二酚、甲酚等限制物质；主打高环保与敏感色稳定。",
        "process": [
            "推荐用量3%（提升力在1%～5%区间较好）",
            "使用无酚产品前必须清洗染缸，清除此前普通助剂残留",
        ],
        "params": [
            "布面残留小于0.1或0.01",
            "水洗、汗渍牢度基本达4级；红黑翠蓝可达3级以上甚至4～5级",
            "固色后放置1小时至60天无色光偏离",
            "不会导致锦氨纶吸水性大幅下降，部分织物甚至提升",
        ],
        "boundaries": [
            "原液完全不含双酚苯酚类，可提供原液报告；布面检出双酚时先查染缸残留与前序助剂",
            "外观由绿转红是储存中折光率变化的物理现象，有效度不变，非不稳定",
            "长期储存不会析出双酚等有害物质",
            "白布防沾色效果较好，可用于印花布白底",
        ],
        "faults": ["布面误检双酚（多因染缸/前序助剂残留）", "客户误判外观绿转红为变质"],
        "certs": ["通过蓝标认证", "原液完全不含双酚、苯酚类限制物质"],
        "cases": ["翠蓝、荧光等敏感色色变显著改善", "印花白底防沾色表现较好", "对比市售竞品牢度有优势"],
    },
    {
        "code": "833",
        "title": "湿摩擦牢度提升剂 833（效果最好）",
        "positioning": "通用性与效果最好的湿擦产品，主攻效果；去年销量最大（约500吨）。",
        "process": [
            "常规用量约30g/L，效果不足可提到50～80g/L",
            "弱阳离子型，浅黄至深黄透明粘液；浸轧/浸渍工艺",
        ],
        "params": [
            "可在原有基础上提升湿摩擦牢度1～1.5级",
            "与硅油或柔软剂同用影响较小",
            "稳定性中等（电导率/金属离子环境敏感）",
        ],
        "boundaries": [
            "稳定性中等：水质差、水温高、同浴固色剂多时易破乳出湿擦斑",
            "不含防腐剂；标品浓度约30%，自行开稀需评估稳定性",
            "涂料印花难提升；化纤面料湿擦提升较难",
        ],
        "faults": ["水质/水温不佳时破乳出湿擦斑", "大机效果弱于小样（带液率下降），需加大用量"],
        "certs": ["环保型：不含丙酮、重金属和甲醛"],
        "cases": ["各布类提升明显，销量约500吨/年", "效果优先场景首选833或8667"],
    },
    {
        "code": "8667",
        "title": "湿摩擦牢度提升剂 8667（效果+稳定兼顾）",
        "positioning": "在833基础上进一步提升稳定性，效果与稳定兼顾；今年主推明星产品，已销售近200吨。",
        "process": ["弱阳离子型湿擦提升剂，浸轧/浸渍工艺", "常规用量约30g/L，难提面料可提高用量"],
        "params": [
            "效果保持833同级提升能力（约1～1.5级）",
            "夏天天气热时不易破乳出湿擦斑",
        ],
        "boundaries": ["适合水质一般但需要效果的工厂", "极端水质/高温苛刻工况优先831B或868"],
        "faults": ["若仍出斑，先查水质、布面残留、同浴沉淀与工作液温度"],
        "certs": ["环保型：不含丙酮、重金属和甲醛"],
        "cases": ["Q&A：天气热到30多度时效果依然稳定", "主推明星产品，已销近200吨"],
    },
    {
        "code": "831B",
        "title": "湿摩擦牢度提升剂 831B（高稳定性）",
        "positioning": "高稳定性湿擦产品，适合工厂苛刻工况：水温高、水质差、同浴固色剂多。",
        "process": [
            "浸轧/浸渍工艺，常规约30g/L，难提面料可到80g/L",
            "水质差、水温高或同浴固色剂多时优先选高稳定性型号",
        ],
        "params": ["提升湿摩擦牢度3～4级", "弱阳离子型，浅黄至深黄透明粘液"],
        "boundaries": [
            "适用夏季水槽直晒水温达40～50℃以上、冷却水水温偏高",
            "适用水质硬度达六七百/七八百ppm（如山东）、未处理干净的混用水或河水",
            "同浴固色剂多时湿擦与固色剂易反应出湿擦斑，优先831B/868",
        ],
        "faults": ["同浴固色剂过多易起反应出湿擦斑", "831B与硅油同浴部分场景到不了3级，可提至80g/L"],
        "certs": ["环保型：不含丙酮、重金属和甲醛"],
        "cases": ["亨德利返修布提至80g/L达标", "831B与硅油同浴不足三级时提量后效果OK"],
    },
    {
        "code": "868",
        "title": "湿摩擦牢度提升剂 868（高稳定+全工艺）",
        "positioning": "高稳定性湿擦产品，浸轧与浸渍皆可用；牛仔定型效果好，可做蓝标出口。",
        "process": [
            "浸轧、浸渍两种工艺均适用",
            "高效后整理：缸内固色 + 定型机上868湿擦与硅油同浴",
        ],
        "params": [
            "提升湿摩擦牢度3～4级",
            "闪点约70℃，7月已通过蓝标认证，出口OK",
        ],
        "boundaries": [
            "对全棉效果OK，具体看客户水质；手感与普通湿擦产品相当",
            "加湿擦后正常烘干可达效果，过定型机温度过高会打折扣",
            "化纤面料湿擦难提升时可试23172或868",
        ],
        "faults": ["工作液温度过高可能影响效果", "牛仔口袋布沾色与防粘存在矛盾，可少量用防染膏"],
        "certs": ["蓝标认证（7月通过）", "闪点约70℃，出口合规", "环保型：不含丙酮、重金属和甲醛"],
        "cases": ["土耳其水温五六十年牛仔市场：868不破乳且效果OK（旧款819易破乳）", "广州景兴、国泰留香：缸内固色后定型机做湿擦+硅油"],
    },
    {
        "code": "7891",
        "title": "三合一染剂 7891（锦纶）",
        "positioning": "锦纶三合一染剂：高匀染、低移染，缩短染色-固色流程，降本节水；与HT-766相容性好。",
        "process": [
            "方案一：升温至80℃加入三合一染剂（省时，有色花风险）",
            "方案二：染色后降温至80℃再加入（品质更好，耗时略增）",
            "与固色剂HT-766可同浴，建议搭配比例1:6",
        ],
        "params": [
            "外观黄色透明液体，含量60%多，粘度约5",
            "适用锦纶、混纺及羊毛混纺织物；酸性和中性染料",
            "两套工艺可节省多道水洗，约省120元/吨",
        ],
        "boundaries": [
            "与HT-766在40℃/70℃/98℃均无混浊，可同浴防固色斑（竞品58℃易混浊）",
            "常温稀释放置5小时无沉淀，相容性好，适配不同水质，降低水质要求",
            "对灰色较友好；匀染/移染/热稳定/分散增容/钙离子相容性综合表现好",
        ],
        "faults": ["传统多道固色流程易色花、色斑、成本高", "低温市场（如江苏冬天）建议做24小时冷冻测试确认"],
        "certs": ["可申请环保达标，含限制性产品内容管控"],
        "cases": ["普通订单可降一两成本，高端订单满足更高品质", "与HT-766协同更有效防固色斑，缩短流程节能降本"],
    },
    {
        "code": "fault-wet-rub",
        "title": "湿擦斑故障诊断卡",
        "positioning": "湿擦出斑原因与处置决策卡：先引导客户自查工艺，多数并非产品不行。",
        "process": [
            "换用水质较好的水",
            "控制布面残留（阴离子助剂及碱，梭织布尤甚）",
            "湿擦与固色剂建议分浴处理",
            "化药顺序：湿擦与硅油/固色剂原液不能直接混合，先将一种配成工作液，再慢慢加入另一种并不断搅拌",
            "以上均无法实现时更换高稳定性型号（831B或868）",
        ],
        "params": ["清洗：强力皂洗粉3～4g/L（过多会引起布面色变）；冰醋酸清洗会残留酸味，客户常不接受"],
        "boundaries": [
            "四类主因：①水质太硬/太差（金属离子盐分多）②布面清洗不充分③固色剂与柔软剂过量同浴（易沉淀；部分硅油含阴离子稳定剂）④工作液温度过高（定型后布温高使槽液迅速升至40～50℃）",
            "已出斑时先确保板能完全清洗；面料可回收则可试重加湿擦或促进剂+湿擦，须先测试不可盲推",
        ],
        "faults": ["破乳出斑", "沉淀出斑", "高温浑浊破乳", "布面残留导致斑渍"],
        "certs": [],
        "cases": ["优先推荐皂洗粉而非冰醋酸", "换831B/868解决高温高硬水质出斑"],
    },
    {
        "code": "guide-wen-wen",
        "title": "湿擦选型「望闻问切」决策卡",
        "positioning": "像医生一样引导客户提供水质、水温、工艺、布种信息，再针对性推荐湿擦产品与方案。",
        "process": [
            "望闻问切四问：①水质②水温③使用工艺（浸轧/浸渍/喷淋）④布种与牢度（针织/梭织/印花/皮革）",
            "方案一提高用量：常规30g/L，可至50～80g/L（大机带液率低于小样）",
            "方案二二次定型：先过30g/L湿擦定型烘干，再湿擦与硅油同浴",
            "方案三分步整理：湿擦与硅油/固色剂分开过；有双轧槽可一步法（一槽湿擦、一槽硅油固色，或喷淋过湿擦）",
            "方案四搭配促进剂：先过促进剂3～8g/L烘干后再湿擦，或促进剂1～3g/L皂洗过水后再湿擦",
        ],
        "params": [
            "效果优先→833或8667；稳定性优先→831B或868；牛仔定型→868",
            "促进剂过量易与湿擦反应生成沉淀，须控量并先做小样",
        ],
        "boundaries": [
            "活性染料印花湿擦有效；涂料印花市面上大部分湿擦难提升",
            "化纤面料湿擦较难提升，可试23172或868",
            "日标（2N、曲面、约100次）与国标/ISO/美标（9N、10～20次）仪器结果基本无对比性，需先问清测试标准",
        ],
        "faults": ["未问清水质水温工艺导致推错型号", "小样OK大货不OK（带液率差异）"],
        "certs": [],
        "cases": ["留香客户硅油120～150g/L同浴不OK→二次定型解决", "中辉校服单湿擦+硅油+固色同浴不OK→分步整理达标", "黄埔返修布→促进剂5g/L烘干后轧湿擦OK"],
    },
    {
        "code": "HT-5095",
        "title": "无醛固色剂 HT-5095",
        "positioning": "无醛固色剂，形成不溶性色淀+表面重层包覆+共价交联三重固色；特深色可达4级。",
        "process": [
            "常规用量约20g/L；难做牢度可提高用量",
            "长车工艺已推广两年并完成迭代升级",
            "与硅油软油兼容，可在定型阶段同浴",
        ],
        "params": [
            "外观浅色，通过蓝标认证",
            "测试3～30g/L，实际3～50g/L甚至60g/L均有提升力",
            "低用量3g/L也能明显提高色牢度",
        ],
        "boundaries": [
            "长车染色出斑多因使用时间延长或与水物质结合，可改用改良款HT-5095",
            "色光影响因织物染料而异，敏感客户量产前打样确认",
            "亲水性影响看结构：5096优于5095；手感更小可看HT-5094/HT-590Y",
            "返修推荐涂布返修工艺",
        ],
        "faults": ["长车使用周期长出斑", "固色后色光变化（需打样）"],
        "certs": ["蓝标认证"],
        "cases": ["20g/L对比市售竞品牢度有优势", "特深色可达4级"],
    },
    {
        "code": "HT-6951",
        "title": "低色变硅油组合（HT-6186-10 / HT-3161G / HT-6951）",
        "positioning": "低色变+好手感硅油矩阵，切入降本市场；棉类与化纤类均有对应风格。",
        "process": ["柔软整理；可按客户浓度需求匹配开稀", "HT-3161G高浓可2～4倍使用；HT-6951蓬松高浓可开放到4倍"],
        "params": [
            "棉类：HT-6186-10含固27%亲水；HT-3161G含硅47%高浓非亲水",
            "化纤类：HT-6951软滑型含固27%亲水；蓬松型含硅47%高浓亲水",
            "棉类色变控制约0.5；化纤类色变0.3以内",
        ],
        "boundaries": [
            "化纤类适用于尼龙、涤纶、混纺；棉类适用棉及部分化纤",
            "与阳离子固色剂相容性好",
            "部分硅油含阴离子稳定剂，与阳离子湿擦混合会降低稳定性，慎同浴",
        ],
        "faults": ["印花面硅油斑", "布面异味（馊味/酸味/烧焦味）", "黑色布偏红光/偏黄外观差异"],
        "certs": ["低色变系列上半年出货200吨以上，多地复购"],
        "cases": ["广东、江苏、浙江、福建、广西等地客户在用", "手感丰满蓬松/软滑，不因低色变牺牲手感"],
    },
]

# 检索用关键词（不进入产品卡字段契约）
_CARD_MATCH_HINTS: dict[str, set[str]] = {
    "HT-766": {"HT-766", "766", "同浴", "固色", "染固", "省水", "省时", "匀染剂", "TY1", "灰色", "色变", "锦纶"},
    "HT-790": {"HT-790", "790", "无酚", "双酚", "苯酚", "环保", "沾色", "翠蓝", "荧光", "残留", "白布", "印花"},
    "833": {"833", "湿擦", "湿摩擦", "摩擦牢度", "效果最好", "提级", "通用型", "销量"},
    "8667": {"8667", "湿擦", "湿摩擦", "摩擦牢度", "稳定", "破乳", "夏天", "热"},
    "831B": {"831B", "831b", "湿擦", "湿摩擦", "高稳", "水质", "水温", "硬度", "同浴固色", "苛刻"},
    "868": {"868", "湿擦", "湿摩擦", "高稳", "浸轧", "浸渍", "牛仔", "定型", "闪点", "蓝标", "出口", "土耳其"},
    "7891": {"7891", "三合一", "染剂", "锦纶", "匀染", "移染", "缩短流程", "同浴", "766"},
    "fault-wet-rub": {"湿擦斑", "出斑", "破乳", "斑", "皂洗", "返修", "沉淀", "故障", "原因"},
    "guide-wen-wen": {"望闻问切", "选型", "推荐", "水质", "水温", "工艺", "布种", "促进剂", "二次定型", "分步", "方案"},
    "HT-5095": {"HT-5095", "5095", "无醛", "甲醛", "长车", "固色", "特深色", "蓝标"},
    "HT-6951": {"HT-6951", "6951", "HT-6186", "3161G", "硅油", "低色变", "手感", "柔软", "亲水", "蓬松", "软滑"},
}

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
