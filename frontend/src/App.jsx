import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { api, apiAudio, apiForm } from "./api";
import { AudioPlayer } from "./audio";
import { AutoReadToggle, MicButton, PlayButton } from "./voice";
import "./styles.css";

const TRAINING_TYPES = ["客户情景陪练", "商机推进教练"];
const OPPORTUNITY_MODE = "商机推进教练";

const opportunityStages = [
  {
    name: "了解商机",
    note: "拿到有效线索，建立直接沟通入口，并约到首次拜访。",
    flow: [
      ["线索获取", "找到潜在客户来源，判断是否值得进入跟进。"],
      ["加微信", "建立直接沟通入口，方便后续资料和拜访安排。"],
      ["约拜访", "把线上线索推进到一次明确的客户接触。"],
    ],
  },
  {
    name: "确认商机",
    note: "确认客户真实需求，尽快取得样品，并推动再次拜访。",
    flow: [
      ["首次拜访", "确认客户需求、使用场景和关键联系人。"],
      ["取得样品", "拿到样品或工艺条件，为后续方案论证做准备。"],
      ["未拿到样品", "识别阻碍原因，判断客户意愿或内部限制。"],
      ["再次拜访", "针对未完成事项继续推进客户接触。"],
    ],
  },
  {
    name: "方案论证",
    note: "围绕打样、报告、送样和试样反馈推进方案验证。",
    flow: [
      ["内部打样", "根据样品和需求组织内部方案验证。"],
      ["出具报告", "形成客户可判断的检测、对比或方案依据。"],
      ["送样", "把方案推进到客户试样环节。"],
      ["客户试样", "跟进试样反馈，确认通过或未通过原因。"],
      ["试样通过", "把技术验证转入商务条件确认。"],
      ["试样未通过", "复盘原因，决定是否重新打样。"],
      ["分析原因重新打样", "针对问题调整方案并再次验证。"],
    ],
  },
  {
    name: "商务谈判",
    note: "处理报价、价格异议、账期和交付条件。",
    flow: [
      ["报价", "给出报价并解释价值、成本和交付边界。"],
      ["商务谈判", "围绕价格、账期、交付和责任条件达成一致。"],
    ],
  },
  {
    name: "销售成交",
    note: "推动合同签订，并保障订单交付边界清晰。",
    flow: [
      ["签订合同", "确认合同条款、价格、交付和责任边界。"],
      ["订单交付", "推动订单按时间、质量和服务要求交付。"],
    ],
  },
  {
    name: "回款",
    note: "跟进回款事项，稳定服务体验，并推动客户复购。",
    flow: [
      ["跟进回款", "根据账期和约定节奏推进回款。"],
      ["服务", "稳定客户服务体验，减少回款和复购阻力。"],
      ["复购", "在服务稳定后推动下一轮需求确认。"],
    ],
  },
];

const stageTrainingGoals = {
  了解商机: [
    { id: "lead", name: "线索判断", desc: "判断线索是否值得进入跟进，并明确客户来源。" },
    { id: "visit", name: "首次触达", desc: "建立直接沟通入口，完成微信或电话连接。" },
    { id: "stalled", name: "约到拜访", desc: "把线上线索推进到一次明确的客户接触。" },
  ],
  确认商机: [
    { id: "stalled", name: "需求澄清", desc: "确认客户真实需求、使用场景和判断标准。" },
    { id: "sample", name: "取得样品", desc: "推动客户提供样品或工艺条件。" },
    { id: "stakeholder", name: "关键人确认", desc: "找到采购、技术或老板中的关键影响人。" },
    { id: "visit", name: "再次拜访", desc: "针对未完成事项推动下一次客户接触。" },
  ],
  方案论证: [
    { id: "technical", name: "技术交涉", desc: "解释工艺、产品方案或测试条件。" },
    { id: "trial", name: "试样推进", desc: "推动客户完成试样并给出反馈。" },
    { id: "report", name: "报告讲解", desc: "把检测、对比或方案依据讲清楚。" },
    { id: "stalled", name: "未通过复盘", desc: "试样未通过时确认原因并推动重新打样。" },
  ],
  商务谈判: [
    { id: "price", name: "价格异议", desc: "客户认为报价高，不愿替换现有供应商。" },
    { id: "contract", name: "条件谈判", desc: "围绕价格、账期、交付和责任条件收口。" },
    { id: "report", name: "报价解释", desc: "解释报价背后的稳定性、服务和交付价值。" },
    { id: "stalled", name: "成交推进", desc: "客户犹豫时锁定下一步动作和时间点。" },
  ],
  销售成交: [
    { id: "contract", name: "合同签订", desc: "推动合同条款、价格和交付边界确认。" },
    { id: "delivery", name: "订单交付", desc: "确认订单交付时间、质量和服务要求。" },
    { id: "stakeholder", name: "责任边界", desc: "明确客户与内部的责任人和交付边界。" },
  ],
  回款: [
    { id: "payment", name: "回款交涉", desc: "客户拖延付款或账期压力大。" },
    { id: "service", name: "服务稳定", desc: "用服务体验降低回款和复购阻力。" },
    { id: "retention", name: "老客维护", desc: "客户订单减少或出现断单风险。" },
    { id: "stalled", name: "复购推进", desc: "在服务稳定后推动下一轮需求确认。" },
  ],
};

const trainingGoals = stageTrainingGoals["商务谈判"];

const customerDifficultyOptions = ["标准", "刁钻", "高压"];
const customerPersonalityOptions = ["谨慎型", "压价型", "专业型", "敷衍型"];
const customerConcernOptions = ["价格", "交期", "品质", "售后"];

const trainingTemplates = [
  {
    id: "price-objection",
    title: "价格异议",
    subtitle: "客户认为报价偏高",
    training_type: "客户情景陪练",
    stage: "商务谈判",
    goal: "价格异议",
    customer_type: "新客户，价格敏感",
    product_name: "活性染料固色盐",
    product_need: "稳定交付，但希望先压低采购成本",
    background: "客户正在比较多家供应商，认为当前报价偏高，希望先降价再继续谈。",
    customer_difficulty: "高压",
    customer_personality: "压价型",
    customer_concern: "价格",
  },
  {
    id: "delivery-risk",
    title: "交期确认",
    subtitle: "客户担心交付延误",
    training_type: "客户情景陪练",
    stage: "方案论证",
    goal: "交期保障",
    customer_type: "渠道客户，关注交期",
    product_name: "活性染料固色盐",
    product_need: "按期交付，避免影响下游排产",
    background: "客户担心旺季交付不稳定，要求说明排产、备货和异常处理方案。",
    customer_difficulty: "刁钻",
    customer_personality: "谨慎型",
    customer_concern: "交期",
  },
  {
    id: "quality-proof",
    title: "品质质疑",
    subtitle: "客户要求稳定性依据",
    training_type: "客户情景陪练",
    stage: "方案论证",
    goal: "技术质疑",
    customer_type: "技术型客户，关注工艺",
    product_name: "活性染料固色盐",
    product_need: "确认稳定性、测试条件和返工风险",
    background: "客户技术负责人要求看到测试条件、稳定性数据和异常处理边界。",
    customer_difficulty: "刁钻",
    customer_personality: "专业型",
    customer_concern: "品质",
  },
  {
    id: "stalled-opportunity",
    title: "商机停滞",
    subtitle: "资料发出后客户没有推进",
    training_type: OPPORTUNITY_MODE,
    stage: "确认商机",
    goal: "商机停滞",
    customer_type: "新客户，内部决策不清晰",
    product_name: "活性染料固色盐",
    product_need: "确认关键人和下一步测试条件",
    background: "客户收资料后没有明确反馈，需要重新推动关键人参与和下一步动作。",
    last_contact: "客户说先内部看看资料，之后一直没有明确反馈。",
    decision_blocker: "关键人未参与",
    next_milestone: "约到关键人会议",
    stakeholder: "采购已沟通，技术负责人还未参与",
    customer_difficulty: "标准",
    customer_personality: "敷衍型",
    customer_concern: "售后",
  },
  {
    id: "payment-followup",
    title: "回款推进",
    subtitle: "客户拖延付款节点",
    training_type: "客户情景陪练",
    stage: "回款",
    goal: "回款交涉",
    customer_type: "老客户，流程较慢",
    product_name: "活性染料固色盐",
    product_need: "确认付款流程、责任人和预计时间",
    background: "客户已经确认订单和交付，但付款流程迟迟没有明确时间。",
    customer_difficulty: "标准",
    customer_personality: "谨慎型",
    customer_concern: "售后",
  },
  {
    id: "payment-quality-objection",
    title: "回款异议",
    subtitle: "客户以质量问题为由压款",
    training_type: "客户情景陪练",
    stage: "回款",
    goal: "回款交涉",
    customer_type: "老客户，订单减少",
    product_name: "湿摩擦牢度提升剂",
    product_need: "先解决质量问题再付款",
    background: "客户反馈某批次湿摩擦牢度不达标，以此为由暂缓付款；该批次出货前有质检报告和留样，问题可能出在工艺使用端。",
    customer_difficulty: "刁钻",
    customer_personality: "专业型",
    customer_concern: "品质",
  },
  {
    id: "payment-extension",
    title: "账期协商",
    subtitle: "客户资金紧张要求延期",
    training_type: "客户情景陪练",
    stage: "回款",
    goal: "回款交涉",
    customer_type: "老客户，流程较慢",
    product_name: "活性染料固色盐",
    product_need: "本批先付部分、尾款延后两个月",
    background: "客户下游回款慢，现金流紧张，提出本批先付50%、尾款延后60天，希望维持长期合作。",
    customer_difficulty: "高压",
    customer_personality: "压价型",
    customer_concern: "售后",
  },
  {
    id: "cold-call-phone",
    title: "电话陌拜",
    subtitle: "首次电话接触染厂采购",
    training_type: "客户情景陪练",
    stage: "了解商机",
    goal: "首次触达",
    customer_type: "新客户，价格敏感",
    product_name: "亲水柔软硅油",
    product_need: "破冰并约到微信",
    background: "通过行业名录拿到某针织染厂采购的电话，这是第一次电话联系，目标是在30秒内破冰、了解当前供应情况并约到微信。",
    customer_difficulty: "高压",
    customer_personality: "敷衍型",
    customer_concern: "价格",
  },
  {
    id: "new-mill-visit",
    title: "新厂陌拜",
    subtitle: "首次拜访新投产染厂",
    training_type: OPPORTUNITY_MODE,
    stage: "了解商机",
    goal: "约到拜访",
    customer_type: "新客户，内部决策不清晰",
    product_name: "湿摩擦牢度提升剂",
    product_need: "首次拜访建立印象并约到关键人",
    background: "目标客户是本地新投产的针织染厂，供应商尚未定型，同行已开始接触；通过行业朋友转介绍获得联系入口。",
    last_contact: "通过转介绍获得联系方式，尚未正式接触。",
    decision_blocker: "关键人未参与",
    next_milestone: "约到首次拜访",
    stakeholder: "暂无直接联系人，采购与技术的决策关系未知",
    customer_difficulty: "标准",
    customer_personality: "敷衍型",
    customer_concern: "交期",
  },
];

const standardReplies = {
  线索判断: "我想先确认一下贵司当前是否真的有替换或新增供应的需求。方便的话，我们先对齐使用场景、当前供应痛点和预计推进时间，再判断是否值得进入下一步。",
  首次触达: "您好，我这边主要想先了解贵司当前用料和供应稳定性情况。如果合适，我可以先发一份简要资料，后续再约一个更具体的沟通时间。",
  约到拜访: "为了不只停留在资料沟通，我建议约一次简短拜访，把使用场景、样品条件和关键关注点一次性确认清楚。",
  需求澄清: "我先不急着推荐方案，想确认三个问题：当前使用场景是什么、最在意的指标是什么、这次评估由谁来判断是否通过。",
  取得样品: "如果要判断方案是否适配，最好先拿到样品或工艺条件。您看我们是否可以先确认样品规格和测试标准？",
  关键人确认: "这件事后续会涉及采购、技术和使用端判断。为了避免来回传话，我们能否把关键评估人一起拉进下一次沟通？",
  再次拜访: "上次沟通后还有几个点没有收口，我建议再约一次，把样品、测试条件和下一步责任人明确下来。",
  价格异议: "我理解您对价格敏感。我们先不急着谈降价，我想先和您确认三件事：稳定性损耗、交付周期风险，以及这次测试通过后能否进入下一步技术确认。",
  商机停滞: "我担心这个项目现在卡在下一步责任人不清晰。我们能不能先约一次 20 分钟沟通，把技术、采购和测试条件一次性确认下来？",
  技术交涉: "这个问题我建议用测试条件来对齐。您方便把当前工艺参数和评判标准发我吗？我会按同一标准给出对比说明和样品验证建议。",
  试样推进: "现在关键不是继续讨论概念，而是把试样条件、评判标准和反馈时间定下来。您看这周能否先安排一次试样确认？",
  报告讲解: "这份报告我想重点和您对齐三点：测试条件是否一致、关键指标差异在哪里、这些差异会怎样影响稳定性和返修成本。",
  未通过复盘: "试样没有通过没关系，我们先把原因拆清楚：是工艺条件、样品匹配、指标要求，还是操作过程影响。确认后再决定是否重新打样。",
  条件谈判: "价格可以谈，但我希望和交付周期、账期、质量责任一起确认，避免只压单价却把后续风险放大。",
  报价解释: "这次报价里不只是单价，还包含稳定性、交付响应和后续服务成本。我们可以先看总使用成本，再判断是否还有调整空间。",
  成交推进: "目前信息已经比较完整，我建议把下一步收敛成一个明确动作：确认关键人、确认条件，或者约定合同节点。",
  合同签订: "我们可以先把合同里最容易反复的价格、交付、质量和责任边界确认掉，避免后面影响订单执行。",
  订单交付: "订单交付我建议先确认时间、质量标准和异常响应方式，这样双方后续执行会更稳。",
  责任边界: "为了避免后续扯皮，我们先明确双方责任人、交付节点、验收标准和异常处理方式。",
  回款交涉: "我理解贵司账期压力，不过这笔款项已经影响后续服务安排。我们能否今天先确认付款节点，如果需要拆分，也请明确金额和日期。",
  服务稳定: "回款和复购都和服务体验有关。我想先确认最近服务里最影响贵司判断的问题，再一起定一个恢复稳定的动作。",
  老客维护: "我想先复盘最近订单减少的真实原因，是价格、库存、交付还是服务体验。确认原因后，我们再一起定一个恢复采购的动作。",
  复购推进: "如果前期服务和交付没有问题，我们可以一起看下一轮需求计划，先确认时间、规格和可能的备货安排。",
};

const defaultForm = {
  training_type: "客户情景陪练",
  stage: "商务谈判",
  goal: "价格异议",
  owner_name: "陈宇",
  customer_name: "锦兴印染",
  customer_type: "老客户，订单减少",
  product_name: "活性染料固色盐",
  product_need: "稳定性和交付保障",
  background: "客户是佛山区 OEM 配套客户，近期订单下滑，对活性染料固色盐价格敏感，同时担心稳定性和交付周期。采购要求先降价，技术负责人还没有参与。",
  last_contact: "客户收了报价和测试资料，但没有确认下一次技术沟通时间。",
  decision_blocker: "关键人未参与",
  next_milestone: "约到关键人会议",
  stakeholder: "采购已参与，技术负责人未参与",
  customer_difficulty: "标准",
  customer_personality: "谨慎型",
  customer_concern: "价格",
  template_id: "",
};

const documentUploadDefaults = {
  source_type: "SOP 与话术",
  tags: "",
};

const documentTypeOptions = ["SOP 与话术", "产品说明书"];
const documentTagPresets = {
  "SOP 与话术": ["销售流程", "商务谈判", "价格异议", "异议处理", "推荐话术", "禁用话术", "评分标准", "回款交涉"],
  "产品说明书": ["产品参数", "工艺条件", "应用场景", "使用方法", "注意事项", "技术边界", "价值表达", "常见问题"],
};
const documentTagKeywords = {
  销售流程: ["销售流程", "流程", "阶段", "商机", "跟进"],
  商务谈判: ["商务谈判", "谈判", "报价", "账期", "交付"],
  价格异议: ["价格", "降价", "报价", "贵", "成本"],
  异议处理: ["异议", "反对", "顾虑", "拒绝", "疑虑"],
  推荐话术: ["推荐话术", "建议话术", "标准话术", "话术"],
  禁用话术: ["禁用", "不要说", "避免", "禁止"],
  评分标准: ["评分", "标准", "考核", "评价"],
  回款交涉: ["回款", "付款", "账期", "催款"],
  产品参数: ["参数", "指标", "含量", "规格", "ph", "粘度"],
  工艺条件: ["工艺", "温度", "时间", "浴比", "条件"],
  应用场景: ["应用", "适用", "场景", "用于", "客户"],
  使用方法: ["使用方法", "用法", "添加", "操作", "步骤"],
  注意事项: ["注意", "事项", "储存", "安全", "避免"],
  技术边界: ["边界", "限制", "不适用", "风险", "兼容"],
  价值表达: ["价值", "优势", "稳定", "成本", "效率"],
  常见问题: ["faq", "常见问题", "问题", "解答"],
};
const documentPageSizes = [20, 50, 100];
const chunkStageOptions = ["", "通用", ...opportunityStages.map((item) => item.name)];
const chunkScenarioOptions = [
  "",
  "通用",
  ...new Set(Object.values(stageTrainingGoals).flat().map((item) => item.name)),
];

function App() {
  const [user, setUser] = useState(null);
  const [view, setView] = useState("start");
  const [railCollapsed, setRailCollapsed] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [sessions, setSessions] = useState([]);
  const [session, setSession] = useState(null);
  const [report, setReport] = useState(null);
  const [knowledge, setKnowledge] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [summary, setSummary] = useState(null);
  const [runtimeStatus, setRuntimeStatus] = useState(null);
  const [error, setError] = useState("");

  async function loadRuntimeStatus() {
    const status = await api("/health");
    setRuntimeStatus(status);
    return status;
  }

  async function loadAll() {
    const [sessionList, kb, docs, dash] = await Promise.all([
      api("/training/sessions"),
      api("/knowledge"),
      api("/knowledge/documents"),
      api("/dashboard/summary"),
    ]);
    setSessions(sessionList);
    setKnowledge(kb);
    setDocuments(docs);
    setSummary(dash);
  }

  useEffect(() => {
    let alive = true;
    loadRuntimeStatus()
      .then((status) => {
        if (alive) setRuntimeStatus(status);
      })
      .catch(() => {
        if (alive) setRuntimeStatus(null);
      });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    const token = localStorage.getItem("salesCoachToken");
    if (!token) return;
    api("/auth/me")
      .then((nextUser) => {
        setUser(nextUser);
        return loadAll();
      })
      .catch(() => localStorage.removeItem("salesCoachToken"));
  }, []);

  if (!user) return <Login onLogin={(nextUser) => { setUser(nextUser); setView("start"); loadAll(); }} />;

  const navGroups = [
    { title: "训练流程", items: [["start", "开始训练", "新建训练"], ["chat", "训练对话", "当前对话"]] },
    { title: "复盘成长", items: [["report", "结果报告", "复盘方案"], ["history", "历史记录", "训练留档"], ["dashboard", "能力看板", "个人趋势"]] },
    {
      title: "知识资料",
      items: [["knowledge", user.role === "admin" ? "文档管理" : "文档查看", user.role === "admin" ? "SOP / 产品资料" : "只读资料"]],
    },
  ];
  const pageTitle = {
    ...Object.fromEntries(navGroups.flatMap((group) => group.items.map(([id, title]) => [id, title]))),
    profile: "个人资料",
    modelConfig: "模型配置",
  }[view];

  async function startSession(payload, mode, formContext) {
    setError("");
    const item = await api("/training/sessions", { method: "POST", body: JSON.stringify(payload) });
    setSession(item);
    if (mode === OPPORTUNITY_MODE) {
      const nextReport = await api(`/training/sessions/${item.id}/finish`, { method: "POST" });
      setReport(withSessionMeta(nextReport, item, formContext));
      setView("report");
    } else {
      setReport(null);
      setView("chat");
    }
    loadAll();
  }

  async function resetCurrentChat() {
    if (!session) return;
    const payload = sessionPayloadFromSession(session);
    const nextSession = await api("/training/sessions", { method: "POST", body: JSON.stringify(payload) });
    setSession(nextSession);
    setReport(null);
    setView("chat");
    loadAll();
  }

  async function clearRecords() {
    await api("/training/sessions", { method: "DELETE" });
    setSessions([]);
    setSession(null);
    setReport(null);
    loadAll();
  }

  function logout() {
    localStorage.removeItem("salesCoachToken");
    setAccountOpen(false);
    setSession(null);
    setReport(null);
    setView("start");
    setUser(null);
  }

  return (
    <div className={`app ${railCollapsed ? "rail-collapsed" : ""}`}>
      <aside className="rail">
        <div className="brand">
          <span className="mark" />
          <div className="brand-copy"><h1>销售陪练</h1><p>培训闭环 MVP</p></div>
          <button className="rail-toggle" aria-label={railCollapsed ? "展开侧边栏" : "折叠侧边栏"} title={railCollapsed ? "展开侧边栏" : "折叠侧边栏"} onClick={() => setRailCollapsed(!railCollapsed)}>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 6l-6 6 6 6"></path></svg>
          </button>
        </div>
        <nav className="nav" aria-label="应用导航">
          {navGroups.map((group) => (
            <section className={`nav-group ${group.title === "知识资料" ? "standalone" : ""}`} key={group.title}>
              <p className="nav-group-title">{group.title}</p>
              {group.items.map(([id, title, sub]) => (
                <button key={id} className={`nav-item ${view === id ? "active" : ""} ${id === "start" ? "primary-entry" : ""} ${id === "knowledge" ? "knowledge-entry" : ""}`} onClick={() => setView(id)}>
                  <span className="nav-icon">{navIcon(id)}</span>
                  <span className="nav-label"><b>{title}</b><span className="small">{sub}</span></span>
                </button>
              ))}
            </section>
          ))}
        </nav>
      </aside>

      <main className="main">
        <div className="topbar">
          <div className="topbar-title">
            <h2>{pageTitle}</h2>
            <RuntimeModeBadge runtimeStatus={runtimeStatus} />
          </div>
          <div className="account-menu">
            <button className="account-trigger" type="button" aria-haspopup="menu" aria-expanded={accountOpen} onClick={() => setAccountOpen((value) => !value)}>
              <span className="account-avatar">{accountInitial(user)}</span>
              <span className="account-copy"><b>{user.name}</b><span>{roleName(user.role)}</span></span>
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 10l5 5 5-5"></path></svg>
            </button>
            {accountOpen && (
              <div className="account-popover" role="menu">
                <div className="account-profile">
                  <span className="account-avatar large">{accountInitial(user)}</span>
                  <div><b>{user.name}</b><p>{user.username} · {roleName(user.role)}</p></div>
                </div>
                <button
                  className="account-row"
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setAccountOpen(false);
                    setView("profile");
                  }}
                >
                  <span>个人资料</span>
                  <small>账号信息与权限</small>
                </button>
                {user.role === "admin" && (
                  <button
                    className="account-row"
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      setAccountOpen(false);
                      setView("modelConfig");
                    }}
                  >
                    <span>模型配置</span>
                    <small>DeepSeek V4 Flash / API Key</small>
                  </button>
                )}
                <button className="account-row danger" type="button" role="menuitem" onClick={logout}>
                  <span>退出登录</span>
                  <small>返回登录入口</small>
                </button>
              </div>
            )}
          </div>
        </div>
        <div className="workspace">
          {isMockRuntime(runtimeStatus) && <RuntimeModeNotice />}
          {error && <div className="toast">{error}</div>}
          {view === "start" && <StartTraining onError={setError} onStarted={startSession} recordCount={sessions.length} />}
          {view === "chat" && <Chat session={session} voiceEnabled={runtimeStatus?.voice_configured === true} onError={setError} onSession={setSession} onReset={resetCurrentChat} onReport={(nextReport) => { setReport(withSessionMeta(nextReport, session)); setView("report"); loadAll(); }} />}
          {view === "report" && <Report report={report} />}
          {view === "history" && (
            <History
              sessions={sessions}
              onClear={async () => { try { await clearRecords(); } catch (err) { setError(err.message); } }}
              onOpen={async (item) => {
                setSession(item);
                if (item.status === "completed") {
                  const nextReport = await api(`/training/reports/${item.id}`);
                  setReport(withSessionMeta(nextReport, item));
                  setView("report");
                } else {
                  setReport(null);
                  setView("chat");
                }
              }}
              onRetry={async (item) => {
                const nextSession = await api(`/training/sessions/${item.id}/retry`, { method: "POST" });
                setSession(nextSession);
                setReport(null);
                setView("chat");
                loadAll();
              }}
            />
          )}
          {view === "dashboard" && <Dashboard summary={summary} />}
          {view === "knowledge" && <Knowledge key="knowledge" user={user} items={knowledge} documents={documents} onChanged={loadAll} onError={setError} />}
          {view === "profile" && <Profile user={user} onUser={setUser} onError={setError} />}
          {view === "modelConfig" && user.role === "admin" && <ModelConfig runtimeStatus={runtimeStatus} onSaved={loadRuntimeStatus} onError={setError} />}
        </div>
      </main>
    </div>
  );
}

function isMockRuntime(runtimeStatus) {
  return runtimeStatus?.llm_mode === "mock" || runtimeStatus?.llm_configured === false;
}

function RuntimeModeBadge({ runtimeStatus }) {
  if (!isMockRuntime(runtimeStatus)) return null;
  return <span className="runtime-mode-badge">模拟模式</span>;
}

function RuntimeModeNotice() {
  return (
    <div className="runtime-mode-notice" role="status" aria-live="polite">
      <b>当前为模拟模式</b>
      <span>未接入真实 LLM，客户回复、推荐回复和复盘报告会使用本地模拟与规则兜底结果。</span>
    </div>
  );
}

function roleName(role) {
  return {
    sales: "业务员",
    admin: "管理员",
  }[role] || "用户";
}

function accountInitial(user) {
  const text = user?.name || user?.username || "用户";
  return text.trim().slice(0, 1).toUpperCase();
}

function rolePermissions(role) {
  return {
    sales: ["新建训练与客户对话", "管理自己的训练历史", "查看文档列表和资料片段"],
    admin: ["管理资料与训练记录", "维护账号权限", "配置系统基础能力"],
  }[role] || ["使用基础训练功能"];
}

function Profile({ user, onUser, onError }) {
  const [form, setForm] = useState({ name: user.name || "", password: "" });
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const permissions = rolePermissions(user.role);

  async function submit(event) {
    event.preventDefault();
    setMessage("");
    onError("");

    const payload = { name: form.name.trim() };
    if (form.password.trim()) payload.password = form.password.trim();

    try {
      setSaving(true);
      const nextUser = await api("/auth/me", { method: "PATCH", body: JSON.stringify(payload) });
      onUser(nextUser);
      setForm({ name: nextUser.name || "", password: "" });
      setMessage("个人资料已保存");
    } catch (err) {
      onError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="page profile-page">
      <div className="hero profile-hero">
        <div className="intro">
          <span className="eyebrow">账号中心</span>
          <h3>个人资料</h3>
          <p>维护当前登录账号的基础信息。角色与权限由系统配置，暂不在这里直接修改。</p>
        </div>
        <div className="profile-identity-card">
          <span className="account-avatar profile-avatar">{accountInitial(user)}</span>
          <div>
            <b>{user.name}</b>
            <p>{user.username} · {roleName(user.role)}</p>
          </div>
        </div>
      </div>

      <div className="profile-grid">
        <form className="profile-card profile-editor" onSubmit={submit}>
          <header>
            <div>
              <span className="section-kicker">基础信息</span>
              <h4>账号资料</h4>
            </div>
            <span className="profile-status-pill">当前账号</span>
          </header>
          <div className="profile-form">
            <label className="profile-field">
              <span>登录账号</span>
              <input value={user.username} readOnly />
            </label>
            <label className="profile-field">
              <span>姓名</span>
              <input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} placeholder="请输入姓名" />
            </label>
            <label className="profile-field">
              <span>新密码</span>
              <input
                type="password"
                value={form.password}
                onChange={(event) => setForm({ ...form, password: event.target.value })}
                placeholder="不修改可留空，至少 6 位"
              />
            </label>
          </div>
          <div className="profile-actions">
            {message && <span className="profile-success">{message}</span>}
            <button className="primary" type="submit" disabled={saving}>{saving ? "保存中..." : "保存资料"}</button>
          </div>
        </form>

        <section className="profile-card profile-permissions">
          <header>
            <div>
              <span className="section-kicker">权限范围</span>
              <h4>{roleName(user.role)}</h4>
            </div>
            <span className="profile-role-pill">{user.role}</span>
          </header>
          <div className="profile-meta">
            <div><span>用户 ID</span><b>{user.id}</b></div>
            <div><span>团队</span><b>{user.team_id ? `团队 ${user.team_id}` : "未绑定"}</b></div>
          </div>
          <div className="permission-list">
            {permissions.map((item) => (
              <div className="permission-item" key={item}>
                <span className="permission-dot" />
                <span>{item}</span>
              </div>
            ))}
          </div>
        </section>
      </div>
    </section>
  );
}

function ModelConfig({ runtimeStatus, onSaved, onError }) {
  const [config, setConfig] = useState(null);
  const [form, setForm] = useState({
    api_key: "",
    clear_api_key: false,
    base_url: "https://api.deepseek.com",
    model_name: "DeepSeek V4 Flash",
    model_id: "deepseek-v4-flash",
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [message, setMessage] = useState("");

  useEffect(() => {
    let alive = true;
    api("/settings/llm")
      .then((data) => {
        if (!alive) return;
        setConfig(data);
        setForm({
          api_key: "",
          clear_api_key: false,
          base_url: data.base_url || "https://api.deepseek.com",
          model_name: data.model_name || "DeepSeek V4 Flash",
          model_id: data.model_id || "deepseek-v4-flash",
        });
      })
      .catch((err) => onError(err.message))
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [onError]);

  async function submit(event) {
    event.preventDefault();
    setMessage("");
    setTestResult(null);
    onError("");
    const payload = {
      clear_api_key: form.clear_api_key,
      base_url: form.base_url.trim(),
      model_name: form.model_name.trim(),
      model_id: form.model_id.trim(),
    };
    if (form.api_key.trim()) payload.api_key = form.api_key.trim();

    try {
      setSaving(true);
      const nextConfig = await api("/settings/llm", { method: "PATCH", body: JSON.stringify(payload) });
      setConfig(nextConfig);
      setForm({
        api_key: "",
        clear_api_key: false,
        base_url: nextConfig.base_url,
        model_name: nextConfig.model_name,
        model_id: nextConfig.model_id,
      });
      await onSaved?.();
      setMessage("模型配置已保存");
    } catch (err) {
      onError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function testConnection() {
    setMessage("");
    setTestResult(null);
    onError("");
    try {
      setTesting(true);
      setTestResult(await api("/settings/llm/test", { method: "POST" }));
      await onSaved?.();
    } catch (err) {
      onError(err.message);
    } finally {
      setTesting(false);
    }
  }

  return (
    <section className="page profile-page model-config-page">
      <div className="hero profile-hero">
        <div className="intro">
          <span className="eyebrow">系统设置</span>
          <h3>模型配置</h3>
          <p>配置 DeepSeek 兼容接口。页面只保存运行时配置，不回显完整 API Key。</p>
        </div>
        <div className="profile-identity-card model-status-card">
          <span className={`model-status-dot ${runtimeStatus?.llm_mode === "llm" ? "is-live" : ""}`} />
          <div>
            <b>{runtimeStatus?.llm_mode === "llm" ? "已接入模型" : "模拟模式"}</b>
            <p>{config?.model_id || "deepseek-v4-flash"}</p>
          </div>
        </div>
      </div>

      <div className="profile-grid">
        <form className="profile-card profile-editor" onSubmit={submit}>
          <header>
            <div>
              <span className="section-kicker">DeepSeek</span>
              <h4>连接配置</h4>
            </div>
            <span className="profile-status-pill">{config?.llm_mode === "llm" ? "已启用" : "待配置"}</span>
          </header>
          {loading ? (
            <div className="empty-card">正在读取模型配置...</div>
          ) : (
            <>
              <div className="profile-form">
                <label className="profile-field full">
                  <span>API Key</span>
                  <input
                    type="password"
                    value={form.api_key}
                    onChange={(event) => setForm({ ...form, api_key: event.target.value, clear_api_key: false })}
                    placeholder={config?.has_api_key ? `${config.api_key_masked}，留空则不修改` : "输入 DeepSeek API Key"}
                  />
                </label>
                <label className="profile-field full">
                  <span>Base URL</span>
                  <input value={form.base_url} readOnly title="当前仅支持白名单内的接口地址" />
                </label>
                <label className="profile-field">
                  <span>模型名称</span>
                  <input value={form.model_name} onChange={(event) => setForm({ ...form, model_name: event.target.value })} />
                </label>
                <label className="profile-field">
                  <span>Model ID</span>
                  <input value={form.model_id} onChange={(event) => setForm({ ...form, model_id: event.target.value })} />
                </label>
              </div>
              {config?.has_api_key && (
                <label className="model-clear-key">
                  <input
                    type="checkbox"
                    checked={form.clear_api_key}
                    onChange={(event) => setForm({ ...form, clear_api_key: event.target.checked, api_key: event.target.checked ? "" : form.api_key })}
                  />
                  <span>清除已保存的 API Key</span>
                </label>
              )}
              <div className="profile-actions">
                {message && <span className="profile-success">{message}</span>}
                {testResult && (
                  <span className={`model-test-result ${testResult.ok ? "is-ok" : "is-failed"}`}>
                    {testResult.message} · {testResult.model_id} · {testResult.latency_ms}ms
                  </span>
                )}
                <button className="secondary" type="button" disabled={saving || testing || loading} onClick={testConnection}>
                  {testing ? "测试中..." : "测试连接"}
                </button>
                <button className="primary" type="submit" disabled={saving}>{saving ? "保存中..." : "保存配置"}</button>
              </div>
            </>
          )}
        </form>

        <section className="profile-card profile-permissions">
          <header>
            <div>
              <span className="section-kicker">当前状态</span>
              <h4>{config?.llm_mode === "llm" ? "真实模型" : "本地模拟"}</h4>
            </div>
            <span className="profile-role-pill">{config?.provider || "deepseek"}</span>
          </header>
          <div className="profile-meta model-meta">
            <div><span>API Key</span><b>{config?.has_api_key ? config.api_key_masked : "未配置"}</b></div>
            <div><span>接口模式</span><b>{config?.llm_configured ? "LLM" : "Mock"}</b></div>
            <div><span>Base URL</span><b>{config?.base_url || "https://api.deepseek.com"}</b></div>
            <div><span>Model ID</span><b>{config?.model_id || "deepseek-v4-flash"}</b></div>
          </div>
          <div className="permission-list">
            <div className="permission-item"><span className="permission-dot" /><span>默认地址：api.deepseek.com</span></div>
            <div className="permission-item"><span className="permission-dot" /><span>实际请求使用 Model ID</span></div>
            <div className="permission-item"><span className="permission-dot" /><span>未保存 API Key 时继续使用模拟回复</span></div>
          </div>
        </section>
      </div>
    </section>
  );
}

function Login({ onLogin }) {
  const [form, setForm] = useState({ username: "sales", password: "123456" });
  const [error, setError] = useState("");
  async function submit(event) {
    event.preventDefault();
    try {
      const data = await api("/auth/login", { method: "POST", body: JSON.stringify(form) });
      localStorage.setItem("salesCoachToken", data.token);
      onLogin(data.user);
    } catch (err) {
      setError(err.message);
    }
  }
  return (
    <div className="login-page">
      <form className="login-card" onSubmit={submit}>
        <span className="eyebrow">AI 销售陪练 MVP</span>
        <h1>先跑通真实训练闭环</h1>
        <p>演示账号：sales / admin，密码都是 123456。</p>
        <input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
        <input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
        {error && <p className="error">{error}</p>}
        <button className="primary">登录</button>
      </form>
    </div>
  );
}

function StartTraining({ onStarted, onError, recordCount }) {
  const [form, setForm] = useState(defaultForm);
  const [stageExpanded, setStageExpanded] = useState(false);
  const [setupSaved, setSetupSaved] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const stageTabsRef = useRef(null);
  const isOpportunity = form.training_type === OPPORTUNITY_MODE;
  const stageIndex = Math.max(0, opportunityStages.findIndex((item) => item.name === form.stage));
  const activeStage = opportunityStages[stageIndex];
  const activeGoals = stageTrainingGoals[activeStage.name] || trainingGoals;
  const trainingStep = isSubmitting
    ? { step: "第 3 步 / 3 步", label: "创建训练" }
    : setupSaved
      ? { step: "第 2 步 / 3 步", label: "阶段目标" }
      : { step: "第 1 步 / 3 步", label: "基础信息" };

  async function submit(event) {
    event.preventDefault();
    if (!setupSaved) {
      onError("请先保存客户信息，再进入下一步训练配置。");
      return;
    }
    try {
      setIsSubmitting(true);
      await onStarted(buildTrainingPayload(form), form.training_type, form);
    } catch (err) {
      setIsSubmitting(false);
      onError(err.message);
    }
  }

  function updateSetup(patch) {
    setForm({ ...form, ...patch });
    setSetupSaved(false);
  }

  function saveSetup() {
    if (!form.owner_name.trim() || !form.customer_name.trim() || !form.product_name.trim() || !form.customer_type.trim() || !form.product_need.trim()) {
      onError("请先补齐业务员、客户名称、产品、客户类型和需求。");
      return;
    }
    if (isOpportunity && (!form.last_contact.trim() || !form.stakeholder.trim())) {
      onError("商机推进教练需要补充最近一次沟通结果和关键人参与情况。");
      return;
    }
    onError("");
    setSetupSaved(true);
  }

  function applyTemplate(template) {
    const nextStage = opportunityStages.find((stage) => stage.name === template.stage) || opportunityStages[0];
    const nextGoals = stageTrainingGoals[nextStage.name] || trainingGoals;
    const nextGoal = nextGoals.some((goal) => goal.name === template.goal) ? template.goal : nextGoals[0].name;
    setForm({
      ...form,
      ...template,
      stage: nextStage.name,
      goal: nextGoal,
      template_id: template.id,
    });
    setSetupSaved(false);
    onError("");
  }

  function selectStage(stage) {
    const nextGoals = stageTrainingGoals[stage.name] || trainingGoals;
    const nextGoal = nextGoals.some((goal) => goal.name === form.goal) ? form.goal : nextGoals[0].name;
    setForm({ ...form, stage: stage.name, goal: nextGoal });
    requestAnimationFrame(() => {
      stageTabsRef.current?.querySelector(".stage-tab.active")?.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
    });
  }

  return (
    <section className="page knowledge-page">
      <div className="hero">
        <div className="intro">
          <span className="eyebrow">训练闭环</span>
          <h3>先用一句话发起训练</h3>
          <p className="hint">先选择训练模式并保存客户基础信息，再进入商机阶段、问题描述和训练目标。</p>
        </div>
        <div className="metric-card">
          <span className="small">本地训练记录</span>
          <strong>{recordCount}</strong>
          <p className="small">完成训练后自动保存</p>
        </div>
      </div>
      <form className="panel" onSubmit={submit}>
        <div className="panel-inner">
          <div className={`panel-head ${setupSaved ? "panel-head-saved" : ""}`}>
            {!setupSaved ? (
              <div className={`mode-switch ${isOpportunity ? "opportunity" : ""}`}>
                {TRAINING_TYPES.map((mode) => (
                  <button type="button" key={mode} className={`mode-option ${form.training_type === mode ? "active" : ""}`} onClick={() => updateSetup({ training_type: mode })}>
                    {mode}
                  </button>
                ))}
              </div>
            ) : (
              <span className="panel-head-label">训练配置</span>
            )}
            <span className={`training-step-pill ${isSubmitting ? "is-active" : ""}`} aria-live="polite">
              <span>{trainingStep.step}</span>
              <b>{trainingStep.label}</b>
            </span>
          </div>

          {!setupSaved && <div className="setup-block">
            <div className="template-block">
              <div className="section-title"><h4>常用训练模板</h4><span className="hint">点选模板后可继续微调客户信息和训练目标。</span></div>
              <div className="template-grid">
                {trainingTemplates.map((template, index) => (
                  <button
                    key={template.id}
                    type="button"
                    className={`template-card ${form.template_id === template.id ? "active" : ""}`}
                    onClick={() => applyTemplate(template)}
                  >
                    <span className="template-card-head"><em>模板 {index + 1}</em><span className="template-head-meta"><strong>{template.customer_concern}</strong><i className="template-select-mark" aria-hidden="true" /></span></span>
                    <b>{template.title}</b>
                    <span>{template.subtitle}</span>
                    <small className="template-route">{template.customer_personality} · {template.stage}</small>
                  </button>
                ))}
              </div>
            </div>

            <div className="basic-fields">
              <div className="section-title"><h4>客户信息</h4><span className="hint">默认带出，可按本次训练快速调整。</span></div>
              <div className="form customer-info-form">
                <label>业务员<input value={form.owner_name} onChange={(e) => updateSetup({ owner_name: e.target.value })} /></label>
                <label>客户名称<input value={form.customer_name} onChange={(e) => updateSetup({ customer_name: e.target.value })} /></label>
                <label>产品<input value={form.product_name} onChange={(e) => updateSetup({ product_name: e.target.value })} /></label>
                <label>客户类型<select value={form.customer_type} onChange={(e) => updateSetup({ customer_type: e.target.value })}>{["老客户，订单减少", "新客户，价格敏感", "技术型客户，关注工艺", "渠道客户，关注交期"].map((item) => <option key={item}>{item}</option>)}</select></label>
                <label className="demand-field">需求<input value={form.product_need} onChange={(e) => updateSetup({ product_need: e.target.value })} /></label>
              </div>
              <div className="profile-tuning">
                <label>客户难度<select value={form.customer_difficulty} onChange={(e) => updateSetup({ customer_difficulty: e.target.value })}>{customerDifficultyOptions.map((item) => <option key={item}>{item}</option>)}</select></label>
                <label>客户性格<select value={form.customer_personality} onChange={(e) => updateSetup({ customer_personality: e.target.value })}>{customerPersonalityOptions.map((item) => <option key={item}>{item}</option>)}</select></label>
                <label>核心关注<select value={form.customer_concern} onChange={(e) => updateSetup({ customer_concern: e.target.value })}>{customerConcernOptions.map((item) => <option key={item}>{item}</option>)}</select></label>
              </div>
            </div>

            <div className={`coach-panel ${isOpportunity ? "visible" : ""}`}>
              <div className="coach-panel-inner">
                <div className="section-title"><h4>商机推进诊断</h4><span className="tag">推进教练专用</span></div>
                <div className="form">
                  <label>最近一次沟通结果<input value={form.last_contact} onChange={(e) => updateSetup({ last_contact: e.target.value })} /></label>
                  <label>关键阻碍<select value={form.decision_blocker} onChange={(e) => updateSetup({ decision_blocker: e.target.value })}>{["关键人未参与", "价格未达预期", "样品或测试未完成", "账期或付款压力", "竞品正在替代"].map((item) => <option key={item}>{item}</option>)}</select></label>
                  <label>下一步里程碑<select value={form.next_milestone} onChange={(e) => updateSetup({ next_milestone: e.target.value })}>{["约到关键人会议", "取得样品或测试条件", "确认报价反馈", "确认合同或订单节点", "确认回款时间"].map((item) => <option key={item}>{item}</option>)}</select></label>
                  <label>关键人参与情况<input value={form.stakeholder} onChange={(e) => updateSetup({ stakeholder: e.target.value })} /></label>
                </div>
              </div>
            </div>

            <div className="setup-actions">
              <span className="setup-state">保存后直接展开商机阶段和训练目标。</span>
              <button className="primary" type="button" onClick={saveSetup}>保存并进入下一步</button>
            </div>
          </div>}

          {setupSaved && <div className="training-config" aria-live="polite">
            <div className="info-overview">
              <div className="info-overview-head">
                <div>
                  <span className={`mode-badge ${isOpportunity ? "opportunity" : "scenario"}`}>{form.training_type}</span>
                  <h4>{form.customer_name}<span>{form.owner_name}</span></h4>
                  <p>{form.customer_type} · {form.product_name} · {form.product_need}</p>
                </div>
                <div className="info-actions">
                  <span className="saved-badge">已保存</span>
                  <button className="secondary" type="button" onClick={() => setSetupSaved(false)}>编辑</button>
                </div>
              </div>
              <div className="info-chips">
                {isOpportunity && <span>{form.decision_blocker}</span>}
                {isOpportunity && <span>{form.next_milestone}</span>}
              </div>
            </div>

            <div className="quick-start">
              <div className="section-title"><h4>商机阶段</h4><span className="tag">必选</span></div>
              <div className={`stage-compact ${stageExpanded ? "expanded" : ""}`}>
                <div className="stage-summary-button">
                  <div className="stage-summary-main">
                    <span className="stage-summary-title"><span>商机阶段 · {stageIndex + 1} / {opportunityStages.length}</span><b>{activeStage.name}</b></span>
                  </div>
                  <div className="stage-note-line">
                    <span className="hint">{activeStage.note}</span>
                  </div>
                  <button className="stage-toggle-label" type="button" onClick={() => setStageExpanded(!stageExpanded)}>{stageExpanded ? "收起动作" : "查看动作"}</button>
                </div>
                <div className="stage-track-row">
                  <span className="mini-progress" style={{ "--progress": `${((stageIndex + 1) / opportunityStages.length) * 100}%` }}><span /></span>
                </div>
                <div className="stage-progress" ref={stageTabsRef} style={{ "--stage-index": stageIndex }}>
                  {opportunityStages.map((stage, index) => (
                    <button key={stage.name} type="button" className={`stage-tab ${form.stage === stage.name ? "active" : ""} ${index < stageIndex ? "done" : ""}`} onClick={() => selectStage(stage)}>
                      <b>{stage.name}</b><small>{stage.flow.length} 个动作</small>
                    </button>
                  ))}
                </div>
                <div className="stage-expanded-content">
                  <div className="stage-detail">
                    <div className="stage-summary"><h4>{activeStage.name}</h4><p className="hint">{activeStage.note}</p></div>
                    <div className="flow-list">
                      {activeStage.flow.map(([name, summary], index) => (
                        <div className="flow-item" key={name} style={{ "--i": index }}><span className="flow-index">{index + 1}</span><span><b>{name}</b><small>{summary}</small></span></div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <label className="field full">一句话描述当前客户 / 商机问题<textarea value={form.background} onChange={(e) => setForm({ ...form, background: e.target.value })} /></label>

            <div className="section-title"><h4>训练目标</h4><span className="hint">{activeStage.name}阶段推荐目标，选择一个最贴近当前卡点的训练方向。</span></div>
            <div className="goal-grid">
              {activeGoals.map((goal) => (
                <button key={goal.id} type="button" className={`goal ${form.goal === goal.name ? "active" : ""}`} onClick={() => setForm({ ...form, goal: goal.name })}>
                  <span className="goal-head"><span className="goal-mark" aria-hidden="true">{goalIcon(goal.id)}</span><b>{goal.name}</b></span>
                  <span className="goal-desc">{goal.desc}</span>
                </button>
              ))}
            </div>
            <div className="actions train-submit-actions">
              {isSubmitting ? <span className="submit-waiting" role="status" aria-live="polite"><i /><span>{isOpportunity ? "正在生成推进方案，请稍等。" : "正在创建训练对话，请稍等。"}</span></span> : <span />}
              <button className="primary" disabled={isSubmitting}>
                {isSubmitting && <span className="button-loader" aria-hidden="true"><i /><i /><i /></span>}
                {isSubmitting ? (isOpportunity ? "生成中" : "创建中") : (isOpportunity ? "生成推进方案" : "开始本次训练")}
              </button>
            </div>
          </div>}
        </div>
      </form>
    </section>
  );
}

function Chat({ session, onSession, onReport, onError, onReset, voiceEnabled }) {
  const [text, setText] = useState("");
  const [showExample, setShowExample] = useState(false);
  const [suggestion, setSuggestion] = useState(null);
  const [isSuggesting, setIsSuggesting] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [isFinishing, setIsFinishing] = useState(false);
  const [isVoiceRecording, setIsVoiceRecording] = useState(false);
  const [autoRead, setAutoRead] = useState(() => localStorage.getItem("salesCoachAutoRead") !== "off");
  const [playback, setPlayback] = useState({ key: "", status: "idle" });
  const playerRef = useRef(null);
  const audioCache = useRef(new Map());
  const inputRef = useRef(null);
  const suggestionRef = useRef(null);
  const salesTurns = useMemo(() => session?.messages?.filter((msg) => msg.role === "sales").length || 0, [session]);
  const exampleReply = standardReplies[session?.goal] || standardReplies["价格异议"];

  useEffect(() => {
    playerRef.current = new AudioPlayer();
    audioCache.current = new Map();
    setPlayback({ key: "", status: "idle" });
    return () => {
      playerRef.current?.dispose();
    };
  }, [session?.id]);

  function toggleAutoRead(next) {
    setAutoRead(next);
    localStorage.setItem("salesCoachAutoRead", next ? "on" : "off");
  }

  function messageCacheKey(message, index) {
    return `${session.id}:${message.id ?? index}`;
  }

  async function speakMessage(message, index) {
    if (!playerRef.current) return;
    const key = messageCacheKey(message, index);
    if (playback.key === key && playback.status === "playing") {
      playerRef.current.stop();
      setPlayback({ key: "", status: "idle" });
      return;
    }
    try {
      let blob = audioCache.current.get(key);
      if (!blob) {
        setPlayback({ key, status: "loading" });
        blob = await apiAudio("/voice/speech", { text: (message.content || "").trim() });
        if (!blob || blob.size === 0) throw new Error("语音数据为空");
        audioCache.current.set(key, blob);
      }
      setPlayback({ key, status: "playing" });
      playerRef.current.playBlob(blob, () => {
        setPlayback((current) => (current.key === key ? { key: "", status: "idle" } : current));
      });
    } catch (err) {
      console.error("语音播放失败:", err);
      setPlayback({ key, status: "error" });
    }
  }

  useEffect(() => {
    if (!showExample) return undefined;
    function handlePointerDown(event) {
      if (suggestionRef.current?.contains(event.target)) return;
      setShowExample(false);
    }
    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, [showExample]);

  if (!session) return <Empty title="还没有训练" text="先从开始训练创建一次会话。" />;

  async function send(forcedContent) {
    const content = (forcedContent ?? text).trim();
    if (!content || isSending || isFinishing) return;
    setText("");
    setSuggestion(null);
    setShowExample(false);
    setIsSending(true);
    playerRef.current?.stop();
    setPlayback({ key: "", status: "idle" });
    onSession({ ...session, messages: [...session.messages, { role: "sales", content }] });
    try {
      await api(`/training/sessions/${session.id}/messages`, { method: "POST", body: JSON.stringify({ content }) });
      const updated = await api(`/training/sessions/${session.id}`);
      onSession(updated);
      if (voiceEnabled && autoRead) {
        const lastIndex = updated.messages.map((message) => message.role).lastIndexOf("customer");
        if (lastIndex >= 0) speakMessage(updated.messages[lastIndex], lastIndex);
      }
    } catch (err) {
      onError(err.message);
    } finally {
      setIsSending(false);
    }
  }

  async function finish() {
    if (isFinishing) return;
    setIsFinishing(true);
    try {
      onReport(await api(`/training/sessions/${session.id}/finish`, { method: "POST" }));
    } catch (err) {
      onError(err.message);
      setIsFinishing(false);
    }
  }

  async function toggleSuggestion() {
    const nextOpen = !showExample;
    setShowExample(nextOpen);
    if (!nextOpen || suggestion || isSuggesting) return;
    setIsSuggesting(true);
    try {
      setSuggestion(await api(`/training/sessions/${session.id}/suggestion`, { method: "POST" }));
    } catch (err) {
      onError(err.message);
    } finally {
      setIsSuggesting(false);
    }
  }

  return (
    <section className="page knowledge-page">
      <div className="hero">
        <div className="intro"><span className="eyebrow">客户情景陪练</span><h3>{session.goal}：{session.customer_name}</h3><p className="hint">{session.stage} / {session.training_type} / {session.customer_type}</p></div>
        <div className="metric-card"><span className="small">业务员轮次</span><strong>{salesTurns}</strong><p className="small">{salesTurns >= 3 ? "已满足验收轮次" : "建议至少 3 轮"}</p></div>
      </div>
      <div className="chat">
        <div className="chat-log">
          {session.messages.map((msg, index) => (
            <div key={msg.id ?? index} className={`msg ${msg.role === "sales" ? "sales" : ""}`}>
              <span className="who">{msg.role === "sales" ? "业务员" : "客户"}</span>
              <div className="bubble-row">
                <div className="bubble">{msg.content}</div>
                {voiceEnabled && msg.role === "customer" && (
                  <PlayButton
                    status={playback.key === messageCacheKey(msg, index) ? playback.status : "idle"}
                    onClick={() => speakMessage(msg, index)}
                  />
                )}
              </div>
            </div>
          ))}
          {isSending && <CustomerReplyWaitingPanel />}
        </div>
        <div className="chat-actions">
          <div className="composer-tools">
            <span>{isSending ? "客户正在思考你的回应..." : salesTurns >= 3 ? "已满足验收轮次，可以进入复盘。" : "建议至少完成 3 轮回应。"}</span>
            {voiceEnabled && <AutoReadToggle enabled={autoRead} onChange={toggleAutoRead} />}
            <div ref={suggestionRef} className={`standard-preview ai-suggestion ${showExample ? "open" : ""}`}>
              <button type="button" onClick={toggleSuggestion} aria-expanded={showExample} disabled={isSending || isFinishing}>{isSuggesting ? "生成中" : "AI推荐回复"}</button>
              <div className="standard-popover ai-suggestion-popover">
                <div className="suggestion-popover-head">
                  <span className="suggestion-label">AI 推荐回复</span>
                  <button className="suggestion-close" type="button" aria-label="关闭推荐回复" onClick={() => setShowExample(false)}>×</button>
                </div>
                {isSuggesting ? (
                  <SuggestionLoadingPanel />
                ) : (
                  <>
                    <p>{suggestion?.content || exampleReply}</p>
                    <small>{suggestion?.notice || "AI 推荐回复仅用于训练参考，并不完全适用于实际业务场景。"}</small>
                  </>
                )}
              </div>
            </div>
          </div>
          <div className={`composer-row ${voiceEnabled ? "has-voice" : ""}`}>
            {voiceEnabled && (
              <MicButton
                disabled={isSending || isFinishing}
                onError={onError}
                onRecordingChange={setIsVoiceRecording}
                onResult={(recognized) => send(recognized)}
              />
            )}
            <input ref={inputRef} value={text} disabled={isSending || isFinishing} onChange={(e) => setText(e.target.value)} placeholder={isSending ? "等待客户回复中" : isVoiceRecording ? "正在录音，再次点击麦克风结束" : "输入你的回应"} onKeyDown={(e) => { if (e.key === "Enter") send(); }} />
            <button className="send-button" disabled={!text.trim() || isSending || isFinishing} onClick={() => send()}>{isSending ? "发送中" : "发送"}</button>
          </div>
          {isFinishing && <ReportGeneratingPanel salesTurns={salesTurns} />}
        </div>
      </div>
      <ReviewReadinessPanel salesTurns={salesTurns} isFinishing={isFinishing} onReset={onReset} onFinish={finish} />
    </section>
  );
}

function ReviewReadinessPanel({ salesTurns, isFinishing, onReset, onFinish }) {
  const ready = salesTurns >= 3;
  const remaining = Math.max(3 - salesTurns, 0);
  const title = isFinishing ? "正在生成复盘" : ready ? "可继续对话或进入复盘" : "建议再补一轮";
  const detail = isFinishing
    ? "系统正在整理对话评分、关键话术、知识库依据和复训任务。"
    : ready
      ? "已满足最小轮次，你可以继续补充对话，也可以结束并生成内容复盘。"
      : `当前已完成 ${salesTurns} 轮，建议至少再完成 ${remaining} 轮，让复盘依据更完整。`;
  return (
    <div className={`review-readiness ${ready ? "is-ready" : ""} ${isFinishing ? "is-loading" : ""}`}>
      <div>
        <span className="review-readiness-label">复盘准备</span>
        <b>{title}</b>
        <p>{detail}</p>
      </div>
      <div className="review-readiness-meter" aria-label={`已完成 ${salesTurns} 轮，建议至少 3 轮`}>
        {[0, 1, 2].map((index) => <i key={index} className={index < Math.min(salesTurns, 3) ? "filled" : ""} />)}
      </div>
      {ready ? (
        <div className="review-readiness-actions">
          <button className="secondary finish-button" disabled={isFinishing} onClick={onReset}>重新对话</button>
          <button className="primary finish-button" disabled={isFinishing} onClick={onFinish}>{isFinishing ? "生成报告中" : "结束并生成报告"}</button>
        </div>
      ) : <span className="review-readiness-pending">完成 3 轮后可生成复盘报告</span>}
    </div>
  );
}

function CustomerReplyWaitingPanel() {
  return (
    <div className="msg customer-waiting-msg">
      <span className="who">客户</span>
      <div className="bubble customer-waiting" role="status" aria-live="polite">
        <span className="typing-bubble" aria-hidden="true"><span /><span /><span /></span>
        <div>
          <b>客户正在生成回复</b>
          <p>正在结合你的回应、客户设定和当前训练目标。</p>
        </div>
      </div>
    </div>
  );
}

function SuggestionLoadingPanel() {
  return (
    <div className="suggestion-loading" role="status" aria-live="polite">
      <div className="suggestion-loading-head">
        <span className="suggestion-pulse" aria-hidden="true"><i /><i /><i /></span>
        <div>
          <b>正在生成参考回复</b>
          <p>正在结合客户最新反馈和训练目标。</p>
        </div>
      </div>
      <div className="suggestion-loading-lines" aria-hidden="true">
        <i /><i /><i />
      </div>
    </div>
  );
}

function ReportGeneratingPanel({ salesTurns }) {
  const [elapsed, setElapsed] = useState(0);
  const steps = [
    ["对话梳理", "提取客户异议和业务员关键回应"],
    ["SOP 对照", "匹配知识库依据和风险话术"],
    ["评分生成", "整理能力评分、金句和复训任务"],
  ];
  const activeIndex = Math.min(Math.floor(elapsed / 4), steps.length - 1);
  useEffect(() => {
    const timer = window.setInterval(() => setElapsed((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return (
    <div className="report-generating" role="status" aria-live="polite">
      <div className="report-generation-head">
        <span className="report-pulse" aria-hidden="true"><i /><i /><i /></span>
        <div>
          <b>正在生成复盘报告</b>
          <p>已完成 {salesTurns} 轮回应，正在把本轮对话整理成评分、依据和复训任务。</p>
        </div>
        <em>{elapsed < 60 ? `${elapsed}s` : "即将完成"}</em>
      </div>
      <div className="report-stepper">
        {steps.map(([title, text], index) => (
          <div key={title} className={`report-step ${index < activeIndex ? "done" : ""} ${index === activeIndex ? "active" : ""}`}>
            <div className="report-step-main">
              <span>{index + 1}</span>
              <div><b>{title}</b><small>{text}</small></div>
            </div>
            <div className="report-step-preview" aria-hidden="true"><i /><i /><i /></div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Report({ report }) {
  if (!report) return <Empty title="还没有结果报告" text="完成客户陪练或生成推进方案后，这里会显示评分、依据和下一步建议。" />;
  const isOpportunity = report.training_type === OPPORTUNITY_MODE;
  const diagnosis = report.opportunity_diagnosis;
  const opportunityContext = report.opportunity_context;
  const review = report.conversation_review;
  const sortedScores = [...(report.scores || [])].sort((a, b) => b.value - a.value);
  const priorityScores = [...(report.scores || [])].sort((a, b) => a.value - b.value);
  const averageScore = priorityScores.length
    ? (priorityScores.reduce((sum, item) => sum + (Number(item.value) || 0), 0) / priorityScores.length).toFixed(1)
    : "-";
  const topScore = sortedScores[0];
  const weakScore = sortedScores[sortedScores.length - 1];
  const urgentScores = (priorityScores.filter((item) => (Number(item.value) || 0) <= 2).slice(0, 2).length
    ? priorityScores.filter((item) => (Number(item.value) || 0) <= 2).slice(0, 2)
    : priorityScores.slice(0, 2));
  const urgentNames = urgentScores.map((item) => item.name).join(" / ") || "暂无短板";
  const needRetrain = (weakScore?.value || 0) <= 3;
  const coachVerdict = needRetrain
    ? `${weakScore?.name || "推进动作"}需要补强`
    : `${topScore?.name || "核心能力"}表现稳定`;
  const coachJudgement = weakScore
    ? `本轮最大问题集中在“${weakScore.name}”，客户已经给出反馈，但还需要把下一步推进到明确的人、时间和条件。`
    : "本轮可以承接客户反馈，下一步需要继续把对话收敛到明确推进动作。";
  const retrainFocus = weakScore
    ? `下一轮重点围绕“${weakScore.name}”练习，把客户反馈拆成明确的人员、时间或条件。`
    : "下一轮重点练习确认关键人、时间和测试条件。";
  const speechPair = buildSpeechPair(report, review);
  const opportunityStrategies = normalizeStrategies(report.alternatives);
  const opportunityTodos = normalizeTodos(report.checklist, report.alternatives);
  const opportunityActions = opportunityTodos.map((item) => item.detail).filter(Boolean);
  const primaryOpportunityAction = opportunityTodos[0]?.detail || opportunityStrategies[0]?.text || "把下一步推进动作收敛到一个明确的人员、时间和条件。";
  const opportunityQuestion = opportunityContext?.decision_blocker
    ? `针对“${opportunityContext.decision_blocker}”，直接确认：这件事由谁判断、什么时候能给反馈、需要我们补什么材料？`
    : "直接确认：这件事由谁判断、什么时候能给反馈、需要我们补什么材料？";
  const strategyCards = opportunityStrategies;
  const riskLines = normalizeTextList(report.risk_lines);
  const goodLines = normalizeTextList(report.good_lines);
  const judgmentItems = [
    { label: "当前阶段", value: report.stage || "待确认", text: report.summary || diagnosis?.judgment || "当前应先把客户卡点拆成一个可确认的下一步动作。" },
    { label: "最大卡点", value: opportunityContext?.decision_blocker || "关键阻碍待确认", text: riskLines[0] || diagnosis?.keyRisk || "当前最大风险尚未被拆成可推进动作。" },
    { label: "关键人缺口", value: opportunityContext?.stakeholder || "关键人链路待确认", text: riskLines[1] || goodLines[0] || diagnosis?.keyPeople || "需要确认采购、技术和最终决策人的影响关系。" },
  ];
  const supportScores = (report.scores || []).slice(0, 3);
  const supportCitations = (report.citations || []).slice(0, 2);
  if (isOpportunity) {
    return (
      <section className="page opportunity-plan-page">
        <div className="opportunity-hero">
          <div className="opportunity-summary">
            <span className="eyebrow">推进方案</span>
            <h3>{opportunityContext?.customer_name || report.customer_name || "当前商机"}</h3>
            <p>{report.summary}</p>
            <div className="report-meta"><span>{report.stage}</span><span>{report.goal}</span><span>{opportunityContext?.decision_blocker || "关键阻碍待确认"}</span></div>
          </div>
          <div className="opportunity-score">
            <span>推进成熟度</span>
            <strong>{report.overall_score}</strong>
            <p>辅助判断，不替代下一步动作</p>
          </div>
        </div>

        <section className="opportunity-command">
          <div>
            <span className="section-kicker">优先推进动作</span>
            <h3>{primaryOpportunityAction}</h3>
            <p>{report.summary || diagnosis?.judgment || "当前应先把客户卡点拆成一个可确认的下一步动作。"}</p>
          </div>
          <aside>
            <span>下一次必须问清</span>
            <p>{opportunityQuestion}</p>
          </aside>
        </section>

        <div className="opportunity-grid">
          <section className="opportunity-panel judgment-panel">
            <span className="section-kicker">推进判断</span>
            <div className="judgment-board">
              {judgmentItems.map((item) => (
                <article key={item.label}>
                  <span>{item.label}</span>
                  <b>{item.value}</b>
                  <p>{item.text}</p>
                </article>
              ))}
            </div>
          </section>

          <section className="opportunity-panel strategy-panel">
            <span className="section-kicker">交涉策略</span>
            <div className="strategy-grid">
              {strategyCards.map((item) => <article key={item.title}><b>{item.title}</b><p>{item.text}</p></article>)}
            </div>
          </section>

          <section className="opportunity-panel action-panel">
            <span className="section-kicker">执行清单</span>
            <ol>{opportunityTodos.slice(0, 4).map((item, i) => {
              return (
                <li key={i}>
                  <div>
                    <b>{item.title}</b>
                    <p>{item.detail}</p>
                  </div>
                  <em><small>建议完成</small><strong>{item.due}</strong></em>
                </li>
              );
            })}</ol>
          </section>

          <section className="opportunity-panel score-evidence-panel">
            <span className="section-kicker">风险与依据</span>
            <div className="evidence-brief">
              <article>
                <b>阶段风险</b>
                <p>{riskLines[2] || diagnosis?.stageRisk || "当前阶段需要先确认客户真实卡点。"}</p>
              </article>
              <article>
                <b>知识依据</b>
                <p>{supportCitations[0]?.source || "商机推进规范"}：{supportCitations[0]?.reason || "用于判断推进动作和禁用话术。"}</p>
              </article>
            </div>
            <div className="plan-score-list">{supportScores.map((item) => (
              <div className="plan-score-row" key={item.name}><span>{item.name}</span><b>{item.value}</b><span className="bar" style={{ "--score": item.value }}><span /></span><p>{item.reason}</p></div>
            ))}</div>
          </section>
        </div>

        <details className="report-evidence">
          <summary>查看引用依据</summary>
          <ul>{report.citations.map((item, i) => <li key={i}><b>{item.source}</b><span>{item.reason}</span></li>)}</ul>
        </details>
      </section>
    );
  }
  return (
    <section className="page report-page">
      <div className="report-hero">
        <div className="report-summary">
          <span className="eyebrow">复盘报告</span>
          <h3>{coachVerdict}</h3>
          <p>{report.summary}</p>
          <div className="report-meta"><span>{report.goal}</span><span>{report.stage}</span><span>{needRetrain ? "建议复训" : "可进入下一轮"}</span></div>
        </div>
        <div className="report-score-card">
          <span>综合评分</span>
          <strong>{report.overall_score}</strong>
          <p>{needRetrain ? "优先补强短板维度" : "整体表现达到训练要求"}</p>
        </div>
      </div>

      <div className="coach-report-grid">
        <section className="coach-conclusion">
          <div className="section-kicker">教练结论</div>
          <p className="coach-summary">{coachJudgement}</p>
          <div className="coach-focus-grid">
            <article><span>本轮亮点</span><p>{review?.highlights?.[0] || topScore?.reason || "本轮能围绕客户问题持续回应。"}</p></article>
            <article><span>主要短板</span><p>{weakScore ? `${weakScore.name}：${weakScore.reason}` : "需要继续提升追问深度，把客户反馈拆成可确认事项。"}</p></article>
            <article><span>下一步训练</span><p>{report.checklist?.[0] || report.alternatives?.[0] || "下一轮重点练习确认关键人、时间和测试条件。"}</p></article>
          </div>
          <div className="highlight-line">
            <span>金句</span>
            <p>{review?.quotes?.[0] || "本轮暂无可沉淀金句，下一轮建议形成一句可复用的话术。"}</p>
          </div>
        </section>

        <section className="ability-portrait">
          <div className="section-kicker">能力画像</div>
          <div className="analysis-panel"><AbilityRadar scores={report.scores} /><div className="analysis-copy"><div className="ability-note strong"><span className="mini-label">优势维度</span><div className="ability-note-head"><b>{topScore?.name || "暂无"}</b><strong>{topScore?.value || "-"}</strong></div><p>{topScore?.reason || "完成更多对话后生成优势判断。"}</p></div><div className="ability-note weak"><span className="mini-label">优先提升</span><div className="ability-note-head"><b>{weakScore?.name || "暂无"}</b><strong>{weakScore?.value || "-"}</strong></div><p>{weakScore?.reason || "完成更多对话后生成提升建议。"}</p></div></div></div>
        </section>
      </div>

      <div className="report-detail-grid">
        <section className="report-section next-training-panel">
          <div className="report-section-head">
            <h3>下一轮训练</h3>
            <p>把本轮短板转成下一次开口动作。</p>
          </div>
          <div className="next-training-grid">
            <article className="training-focus-card"><span>复训重点</span><strong>{retrainFocus}</strong><p>先确认人、时间和条件，再进入价格、测试或合同细节。</p></article>
            <article className="training-script-card script-compare-card">
              <span>话术对比</span>
              <div className="script-compare">
                <div className="script-bubble original" title={speechPair.original}><b>原话术</b><p>{speechPair.original}</p></div>
                <div className="script-bubble suggested" title={speechPair.suggested}><b>建议话术</b><p>{speechPair.suggested}</p></div>
              </div>
            </article>
            <article className="training-task-card">
              <span>训练任务</span>
              <div className="task-detail-list">{report.checklist.slice(0, 3).map((item, i) => {
                const task = buildTrainingTask(item, i);
                return (
                  <details className="task-detail" key={i}>
                    <summary>
                      <div className="task-summary-copy">
                        <b>{task.title}</b>
                      </div>
                      <div className="task-summary-meta">
                        <em className="task-due"><small>建议</small><strong>{task.due}</strong></em>
                        <small className="task-toggle"><span className="closed">查看内容</span><span className="opened">收起内容</span></small>
                      </div>
                    </summary>
                    <div className="task-expanded">
                      <div><span>任务目的</span><p>{task.purpose}</p></div>
                      <div><span>训练内容</span><p>{task.detail}</p></div>
                    </div>
                  </details>
                );
              })}</div>
            </article>
          </div>
        </section>
        <section className="report-section compact-score-card">
          <div className="report-section-head">
            <h3>评分明细</h3>
            <p>先看分数和状态，需要时再展开依据。</p>
          </div>
          <div className="score-priority">
            <div>
              <span>优先处理</span>
              <strong>{urgentNames}</strong>
              <p>{weakScore?.reason || "完成更多训练后生成优先处理判断。"}</p>
            </div>
            <b className="score-average"><span>均分</span><em>{averageScore}</em><span>/5</span></b>
          </div>
          <div className="score-list">{priorityScores.map((item) => (
            <div className={`score-row ${scoreToneClass(item.value)}`} key={item.name}>
              <div className="score-row-main"><span>{item.name}</span><b>{scoreLevelLabel(item.value)}</b></div>
              <span className="score">{item.value}</span>
              <span className="bar" style={{ "--score": item.value }}><span /></span>
              <ScoreReason reason={item.reason} />
            </div>
          ))}</div>
        </section>
      </div>

      <details className="report-evidence">
        <summary>查看引用依据</summary>
        <ul>{report.citations.map((item, i) => <li key={i}><b>{item.source}</b><span>{item.reason}</span></li>)}</ul>
      </details>
    </section>
  );
}

function ScoreReason({ reason }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        className={`score-reason-toggle ${open ? "open" : ""}`}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        {open ? "收起依据" : "查看依据"}
      </button>
      {open && <p className="score-reason-panel">{reason || "本项暂无补充依据。"}</p>}
    </>
  );
}

function History({ sessions, onOpen, onRetry, onClear }) {
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const pageSizeOptions = [5, 10];
  const totalPages = Math.max(1, Math.ceil(sessions.length / pageSize));
  const safePage = Math.min(currentPage, totalPages);
  const startIndex = (safePage - 1) * pageSize;
  const visibleSessions = sessions.slice(startIndex, startIndex + pageSize);
  const endIndex = Math.min(startIndex + visibleSessions.length, sessions.length);
  const showPagination = sessions.length > pageSize;

  useEffect(() => {
    setCurrentPage((page) => Math.min(page, totalPages));
  }, [totalPages]);

  return (
    <section className="page">
      <div className="hero">
        <div className="intro"><span className="eyebrow">历史记录</span><h3>训练留档</h3><p className="hint">查看训练报告，或基于上一次问题再次训练。</p></div>
        <div className="metric-card"><span className="small">记录数</span><strong>{sessions.length}</strong><p className="small">当前账号数据</p></div>
      </div>
      <div className="panel">
        <div className="panel-inner">
          <div className="section-title history-title">
            <div>
              <h4>训练历史</h4>
              {!!sessions.length && <p className="small">每页显示 {pageSize} 条，当前 {sessions.length ? startIndex + 1 : 0}-{endIndex} / {sessions.length} 条。</p>}
            </div>
            <div className="history-actions">
              <div className="page-size-switch" aria-label="每页显示条数">
                <span>每页</span>
                {pageSizeOptions.map((size) => (
                  <button
                    className={pageSize === size ? "active" : ""}
                    key={size}
                    type="button"
                    onClick={() => {
                      setPageSize(size);
                      setCurrentPage(1);
                    }}
                  >
                    {size} 条
                  </button>
                ))}
              </div>
              <button className="secondary" onClick={onClear}>清空我的训练记录</button>
            </div>
          </div>
          {!sessions.length && <Empty title="还没有训练记录" text="先完成一次训练，就能在这里看到留档和再次训练入口。" />}
          <div className="records">{visibleSessions.map((item) => (
            <article className="record-item" key={item.id}>
              <div className="record-copy">
                <b>{item.customer_name} / {item.goal}</b>
                <div className="mini-line"><span>{formatDate(item.created_at)}</span><span>{item.training_type}</span><span>{item.stage}</span><span>{item.status}</span></div>
                <p className="small">查看报告，或基于这次记录再次训练。</p>
              </div>
              <div className="record-actions"><button className="secondary" onClick={() => onOpen(item)}>查看报告</button><button className="primary" onClick={() => onRetry(item)}>再次训练</button></div>
            </article>
          ))}</div>
          {showPagination && (
            <div className="pagination-bar" aria-label="训练历史分页">
              <span>第 {safePage} / {totalPages} 页</span>
              <div className="pagination-controls">
                <button className="secondary" onClick={() => setCurrentPage((page) => Math.max(1, page - 1))} disabled={safePage === 1}>上一页</button>
                {Array.from({ length: totalPages }, (_, index) => index + 1).map((page) => (
                  <button
                    className={`page-number${page === safePage ? " active" : ""}`}
                    key={page}
                    onClick={() => setCurrentPage(page)}
                    aria-current={page === safePage ? "page" : undefined}
                  >
                    {page}
                  </button>
                ))}
                <button className="secondary" onClick={() => setCurrentPage((page) => Math.min(totalPages, page + 1))} disabled={safePage === totalPages}>下一页</button>
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function Dashboard({ summary }) {
  if (!summary) return <Empty title="暂无看板数据" text="完成训练后自动生成能力概览。" />;
  const trainingCount = Number(summary.training_count) || 0;
  const completedCount = Number(summary.completed_count) || 0;
  const activeCount = Number(summary.active_count) || Math.max(0, trainingCount - completedCount);
  const averageScore = Number(summary.average_score) || 0;
  const completeRate = trainingCount ? Math.round((completedCount / trainingCount) * 100) : 0;
  const goals = distributionRows(summary.goal_distribution, 5);
  const stages = distributionRows(summary.stage_distribution, 6);
  const scoreAverages = normalizeDashboardScores(summary.score_averages);
  const weakDimensions = [...scoreAverages].filter((item) => item.value > 0).sort((a, b) => a.value - b.value).slice(0, 3);
  const strongDimensions = [...scoreAverages].filter((item) => item.value > 0).sort((a, b) => b.value - a.value).slice(0, 3);
  const weakDimension = weakDimensions[0];
  const strongDimension = strongDimensions[0];
  const topGoal = goals[0];
  const recentScores = Array.isArray(summary.recent_scores) ? summary.recent_scores.slice(-10) : [];
  const scoreTrend = buildScoreTrend(recentScores.map((item) => item.score));
  const latestScore = recentScores[recentScores.length - 1]?.score || averageScore;
  const previousScore = recentScores[recentScores.length - 2]?.score || latestScore;
  const scoreDelta = Math.round((latestScore - previousScore) * 10) / 10;
  const nextFocus = weakDimension?.name || topGoal?.name || "价格异议";
  return (
    <section className="page dashboard-page">
      <div className="hero dashboard-hero">
        <div className="intro"><span className="eyebrow">能力成长</span><h3>个人训练画像</h3><p className="hint">把训练、对话、复盘和历史记录汇总成一个可行动的能力中心：先看状态，再看短板，最后决定下一轮练什么。</p></div>
      </div>
      <div className="profile-metrics">
        <article><span>训练次数</span><strong>{trainingCount}</strong><p>累计训练记录</p></article>
        <article><span>复盘完成</span><strong>{completedCount}</strong><p>{completeRate}% 已形成报告</p></article>
        <article><span>最近均分</span><strong>{averageScore || "-"}</strong><p>{scoreDelta > 0 ? `较上次 +${scoreDelta}` : scoreDelta < 0 ? `较上次 ${scoreDelta}` : "保持稳定"}</p></article>
        <article><span>待完成</span><strong>{activeCount}</strong><p>可继续对话或复盘</p></article>
      </div>
      <div className="profile-grid">
        <section className="profile-panel ability-overview">
          <div className="profile-section-head"><div><span>能力画像</span><h4>七项能力均分</h4></div><p>来自已完成复盘报告的分项评分。</p></div>
          <div className="profile-ability-layout">
            <AbilityRadar scores={scoreAverages} />
            <div className="profile-insight-list">
              <article className="profile-insight strong"><span>优势能力</span><b>{strongDimension?.name || "暂无"}</b><p>{strongDimension ? `${strongDimension.value} / 5，继续沉淀可复用表达。` : "完成复盘后生成优势能力。"}</p></article>
              <article className="profile-insight weak"><span>优先补强</span><b>{weakDimension?.name || "暂无"}</b><p>{weakDimension ? `${weakDimension.value} / 5，建议下一轮集中练习。` : "完成复盘后生成短板判断。"}</p></article>
            </div>
          </div>
        </section>
        <section className="profile-panel action-center">
          <div className="profile-section-head"><div><span>下一步行动</span><h4>本周训练建议</h4></div><p>把数据转成下一轮训练任务。</p></div>
          <div className="action-card primary-action">
            <span>优先练习</span>
            <strong>{nextFocus}</strong>
            <p>{weakDimension ? `围绕“${weakDimension.name}”做 1 次客户情景陪练，并在复盘里确认话术是否更具体。` : "先完成一次客户情景陪练，生成第一份能力画像。"}</p>
          </div>
          <div className="action-steps">
            <span>建议节奏</span>
            <p>3 天内完成 1 次对话训练，随后用同一背景再生成 1 份商机推进方案。</p>
          </div>
        </section>
      </div>
      <div className="profile-grid lower">
        <section className="profile-panel trend-panel">
          <div className="profile-section-head"><div><span>成长趋势</span><h4>最近 10 次得分</h4></div></div>
          <div className="score-trend-line">
            {scoreTrend.points.length ? (
              <svg viewBox={`0 0 ${scoreTrend.width} ${scoreTrend.height}`} role="img" aria-label="最近 10 次训练得分折线趋势">
                <defs>
                  <linearGradient id="scoreTrendArea" x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0%" stopColor="#1a73e8" stopOpacity="0.18" />
                    <stop offset="100%" stopColor="#1a73e8" stopOpacity="0.02" />
                  </linearGradient>
                </defs>
                {scoreTrend.gridLines.map((line) => (
                  <line className="trend-grid-line" key={line.score} x1={scoreTrend.paddingX} x2={scoreTrend.width - scoreTrend.paddingX} y1={line.y} y2={line.y} />
                ))}
                <path className="trend-area-path" d={scoreTrend.areaPath} />
                <path className="trend-line-path" d={scoreTrend.linePath} />
                {scoreTrend.points.map((point) => (
                  <g className="trend-point-group" key={`${point.index}-${point.value}`}>
                    <circle className="trend-point-halo" cx={point.x} cy={point.y} r="9" />
                    <circle className="trend-point" cx={point.x} cy={point.y} r="4.6" style={{ "--point-color": trendScoreColor(point.value) }}>
                      <title>{`第 ${point.index} 次：${point.value} 分`}</title>
                    </circle>
                    <text className="trend-axis-label" x={point.x} y={scoreTrend.height - 8}>{point.index}</text>
                  </g>
                ))}
              </svg>
            ) : <p className="small">完成复盘后生成得分趋势。</p>}
          </div>
        </section>
        <section className="profile-panel distribution-panel">
          <div className="profile-section-head"><div><span>训练结构</span><h4>高频场景与阶段</h4></div><p>看最近训练是否过度集中。</p></div>
          <div className="distribution-columns">
            <div><b>目标 Top 5</b>{goals.length ? goals.map((item) => <DistributionRow item={item} key={item.name} />) : <p className="small">暂无训练目标分布。</p>}</div>
            <div><b>阶段覆盖</b>{stages.length ? stages.map((item) => <DistributionRow item={item} key={item.name} />) : <p className="small">暂无商机阶段分布。</p>}</div>
          </div>
        </section>
      </div>
    </section>
  );
}

function Knowledge({
  user,
  items,
  documents = [],
  onChanged,
  onError,
}) {
  const [form, setForm] = useState(documentUploadDefaults);
  const [file, setFile] = useState(null);
  const fileInputRef = useRef(null);
  const [localDocuments, setLocalDocuments] = useState([]);
  const [selectedDocument, setSelectedDocument] = useState(null);
  const [typeFilter, setTypeFilter] = useState("全部");
  const [isUploading, setIsUploading] = useState(false);
  const [isDraggingFile, setIsDraggingFile] = useState(false);
  const [uploadNotice, setUploadNotice] = useState("");
  const [analysisStatus, setAnalysisStatus] = useState("idle");
  const [analysisSummary, setAnalysisSummary] = useState("");
  const canEdit = user.role === "admin";
  const allDocuments = documents.length ? documents : localDocuments;
  const pageDocuments = typeFilter === "全部" ? allDocuments : allDocuments.filter((item) => item.source_type === typeFilter);
  const selectedTags = splitDocumentTags(form.tags);
  const tagPresets = documentTagPresets[form.source_type] || [];
  const isAnalyzing = analysisStatus === "analyzing";

  useEffect(() => {
    if (documents.length) return;
    refreshLocalDocuments().catch(() => setLocalDocuments([]));
  }, [documents.length]);

  async function refreshLocalDocuments() {
    const nextDocuments = await api("/knowledge/documents");
    setLocalDocuments(nextDocuments);
    return nextDocuments;
  }

  function openFilePicker() {
    if (!isUploading && !isAnalyzing) fileInputRef.current?.click();
  }

  async function prepareFile(nextFile) {
    if (isUploading || isAnalyzing) return;
    if (!nextFile) {
      setUploadNotice("没有选择文件。");
      return;
    }
    setFile(nextFile);
    setAnalysisStatus("analyzing");
    setAnalysisSummary("");
    setUploadNotice("正在分析文件内容，并匹配资料类型和标签。");
    try {
      const formData = new FormData();
      formData.append("source_type", form.source_type);
      formData.append("file", nextFile);
      const result = await apiForm("/knowledge/documents/analyze", formData);
      const nextSourceType = documentTypeOptions.includes(result.source_type) ? result.source_type : form.source_type;
      const allowedTags = documentTagPresets[nextSourceType] || [];
      const nextTags = Array.isArray(result.tags)
        ? result.tags.filter((tag) => allowedTags.includes(tag)).slice(0, 5)
        : [];
      setForm({ source_type: nextSourceType, tags: nextTags.join("、") });
      setAnalysisStatus("ready");
      setAnalysisSummary(result.summary || "已完成文档预分析，可在右侧调整后上传。");
      setUploadNotice("已完成预分析，可确认资料类型和标签后上传文件。");
    } catch {
      const preview = await readDocumentPreview(nextFile);
      const nextSourceType = inferDocumentSourceType(nextFile, form.source_type, preview);
      const nextTags = inferDocumentTags(nextFile, nextSourceType, preview);
      setForm({ source_type: nextSourceType, tags: nextTags.join("、") });
      setAnalysisStatus("error");
      setAnalysisSummary("LLM 预分析暂不可用，已使用本地规则预选资料类型和标签。");
      setUploadNotice("预分析失败，已用本地规则预选；可手动调整后上传。");
    }
  }

  async function uploadSelectedFile(targetFile = file, targetForm = form) {
    if (!targetFile) {
      setUploadNotice("请先选择一个资料文件");
      return onError("请先选择一个资料文件");
    }
    const formData = new FormData();
    formData.append("source_type", targetForm.source_type);
    formData.append("tags", targetForm.tags);
    formData.append("source_name", targetFile.name);
    formData.append("recommended", "根据文档内容生成可引用依据。");
    formData.append("banned", "不要编造文档中没有的信息。");
    formData.append("file", targetFile);
    try {
      setIsUploading(true);
      setUploadNotice("正在上传并解析；如果是同名文件，系统会自动生成新版。");
      await apiForm("/knowledge/documents", formData);
      setFile(null);
      setForm({ ...documentUploadDefaults, source_type: targetForm.source_type });
      setAnalysisStatus("idle");
      setAnalysisSummary("");
      setUploadNotice("已上传，文档版本和片段数量已更新。");
      await onChanged();
      await refreshLocalDocuments();
    } catch (err) {
      setUploadNotice(`上传失败：${err.message}`);
      onError(err.message);
    } finally {
      setIsUploading(false);
    }
  }

  async function uploadDocument(event) {
    event.preventDefault();
    await uploadSelectedFile();
  }

  function cancelUpload() {
    if (isUploading) return;
    setFile(null);
    setForm(documentUploadDefaults);
    setAnalysisStatus("idle");
    setAnalysisSummary("");
    setUploadNotice("");
    setIsDraggingFile(false);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  async function handleFileInputChange(event) {
    await prepareFile(event.target.files?.[0] || null);
    event.target.value = "";
  }

  function handleDragOver(event) {
    event.preventDefault();
    if (!isUploading && !isAnalyzing) setIsDraggingFile(true);
  }

  function handleDragLeave(event) {
    if (event.relatedTarget && event.currentTarget.contains(event.relatedTarget)) return;
    setIsDraggingFile(false);
  }

  function handleDropZoneKeyDown(event) {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    openFilePicker();
  }

  async function handleDrop(event) {
    event.preventDefault();
    setIsDraggingFile(false);
    await prepareFile(event.dataTransfer.files?.[0] || null);
  }

  async function toggleDocument(documentId) {
    try {
      await api(`/knowledge/documents/${documentId}/toggle`, { method: "POST" });
      onChanged();
    } catch (err) {
      onError(err.message);
    }
  }

  async function saveDocument(documentId, payload) {
    try {
      await api(`/knowledge/documents/${documentId}`, { method: "PATCH", body: JSON.stringify(payload) });
      await onChanged();
      await refreshLocalDocuments();
    } catch (err) {
      onError(err.message);
      throw err;
    }
  }

  async function deleteDocument(documentId, title) {
    if (!window.confirm(`确认删除「${title}」？删除后该文档版本和片段都不会再参与引用。`)) return;
    try {
      await api(`/knowledge/documents/${documentId}`, { method: "DELETE" });
      await onChanged();
      await refreshLocalDocuments();
    } catch (err) {
      onError(err.message);
    }
  }

  if (selectedDocument) {
    return (
      <ChunkDetail
        document={selectedDocument}
        onBack={() => setSelectedDocument(null)}
        onError={onError}
      />
    );
  }

  return (
    <section className="page">
      <div className="hero">
        <div className="intro">
          <span className="eyebrow">知识资料</span>
          <h3>{canEdit ? "统一管理 SOP 与产品资料" : "查看 SOP 与产品资料"}</h3>
          <p className="hint">{canEdit ? "上传文件后自动抽取正文、识别片段类型，并作为陪练、复盘和推进方案的引用依据。" : "当前账号可以查看已入库资料和解析片段，资料导入与管理由管理员完成。"}</p>
        </div>
        <div className="metric-card"><span className="small">已上传文档</span><strong>{allDocuments.length}</strong><p className="small">{items.length} 个片段可被检索</p></div>
      </div>

      {canEdit && (
        <form className="panel doc-upload-panel" onSubmit={uploadDocument}>
          <div className="panel-inner knowledge-manager">
            <div className="section-heading">
              <div><h4>导入资料</h4></div>
            </div>
            <div className="upload-box">
              <div
                className={`upload-drop ${file ? "has-file" : ""} ${isDraggingFile ? "is-dragging" : ""}`}
                role="button"
                tabIndex={0}
                aria-disabled={isUploading || isAnalyzing}
                onClick={openFilePicker}
                onKeyDown={handleDropZoneKeyDown}
                onDragOver={handleDragOver}
                onDragEnter={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
              >
                <input ref={fileInputRef} type="file" accept=".txt,.md,.pdf,.docx,text/plain,text/markdown,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={handleFileInputChange} disabled={isUploading || isAnalyzing} />
                <span>{isDraggingFile ? "松开分析" : "选择文件"}</span>
                <b>{file?.name || "拖拽文件到这里，或点击选择"}</b>
                <em>{file ? analysisStatusText(analysisStatus) : "支持 TXT / MD / PDF / DOCX，同名文件自动生成新版"}</em>
                {file && (
                  <div className="upload-file-meta">
                    <i>{fileExtensionLabel(file)}</i>
                    <i>{fileSizeLabel(file.size)}</i>
                  </div>
                )}
              </div>
              <div className="upload-options">
                <div className="upload-option-block">
                  <span className="option-label">资料类型</span>
                  <div className={`mode-switch compact ${form.source_type === "产品说明书" ? "product-doc" : ""}`}>
                    {documentTypeOptions.map((item) => (
                      <button
                        key={item}
                        type="button"
                        className={`mode-option ${form.source_type === item ? "active" : ""}`}
                        disabled={isAnalyzing}
                        onClick={() => setForm({ ...documentUploadDefaults, source_type: item })}
                      >
                        {item}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="upload-option-block">
                  <span className="option-label">标签</span>
                  <div className="tag-preset-grid">
                    {tagPresets.map((tag) => (
                      <button
                        key={tag}
                        type="button"
                        className={selectedTags.includes(tag) ? "selected" : ""}
                        disabled={isAnalyzing}
                        onClick={() => setForm({ ...form, tags: toggleDocumentTag(form.tags, tag) })}
                      >
                        {tag}
                      </button>
                    ))}
                  </div>
                  <p className="micro-hint">标签用于辅助检索，阶段、场景和客户类型会由解析结果自动识别。</p>
                </div>
                <div className={`analysis-status ${analysisStatus}`}>
                  <span>{analysisStatusTitle(analysisStatus)}</span>
                  <p>{analysisSummary || "选择文件后，会先分析内容，再让你确认资料类型和标签。"}</p>
                </div>
              </div>
            </div>
            {file && !isAnalyzing && (
              <div className="upload-confirm-bar">
                <div>
                  <span>确认入库</span>
                  <p>{uploadNotice || "资料类型和标签确认无误后，再上传并生成可检索片段。"}</p>
                </div>
                <div className="upload-confirm-actions">
                  <button className="secondary" type="button" disabled={isUploading} onClick={cancelUpload}>取消上传</button>
                  <button className="primary" type="submit" disabled={isUploading}>
                    {isUploading ? "上传中..." : "确认上传"}
                  </button>
                </div>
              </div>
            )}
          </div>
        </form>
      )}

      <div className="document-toolbar">
        <div>
          <span className="small">文档列表</span>
          <h4>当前资料</h4>
        </div>
        <div className="doc-filter-tabs">
          {["全部", ...documentTypeOptions].map((item) => (
            <button className={typeFilter === item ? "active" : ""} key={item} onClick={() => setTypeFilter(item)}>{item}</button>
          ))}
        </div>
      </div>

      <div className="document-list">
        {pageDocuments.length ? pageDocuments.map((document) => (
          <DocumentCard
            key={document.id}
            document={document}
            canEdit={canEdit}
            onToggle={toggleDocument}
            onOpenChunks={() => setSelectedDocument(document)}
            onSave={saveDocument}
            onDelete={() => deleteDocument(document.id, document.title)}
          />
        )) : <div className="empty-card">{canEdit ? "还没有文档。先上传一份 SOP、话术或产品说明书。" : "还没有可查看的文档。"}</div>}
      </div>
    </section>
  );
}

function DocumentCard({ document, canEdit, onToggle, onOpenChunks, onSave, onDelete }) {
  const current = document.current_version;
  const isActive = document.status === "active";
  const parsed = document.parse_status === "parsed";
  const tags = splitDocumentTags(document.tags);
  const versions = document.versions || [];
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [editForm, setEditForm] = useState({ title: document.title, source_type: document.source_type, tags: document.tags || "", reparse: false });
  const editTags = splitDocumentTags(editForm.tags);
  const editTagPresets = documentTagPresets[editForm.source_type] || [];

  useEffect(() => {
    if (!isEditing) setEditForm({ title: document.title, source_type: document.source_type, tags: document.tags || "", reparse: false });
  }, [document.id, document.title, document.source_type, document.tags, isEditing]);

  async function submitEdit() {
    const title = editForm.title.trim();
    if (!title) return;
    setIsSaving(true);
    try {
      await onSave(document.id, { ...editForm, title });
      setIsEditing(false);
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <article className={`document-card ${document.status === "disabled" ? "is-disabled" : ""} ${isEditing ? "is-editing" : ""} ${canEdit ? "" : "no-actions"}`}>
      <div className="document-main">
        <div className="document-title-row">
          <b>{document.title}</b>
          <span className="doc-type-chip">{document.source_type}</span>
          <span className={`parse-chip ${parsed ? "success" : ""}`}>{parseStatusLabel(document.parse_status)}</span>
        </div>
        <div className="document-tags">
          {tags.length ? tags.slice(0, 5).map((tag) => <span key={tag}>{tag}</span>) : <span>未设置标签</span>}
        </div>
        {document.error_message && <p className="error-line">{document.error_message}</p>}
      </div>
      <div className="document-version-panel">
        <div className="version-metric" title={`共 ${versions.length} 个版本`}>
          <strong>{current?.version_label || "未解析"}</strong>
          <span>版本</span>
        </div>
        <button className="chunk-count-button" type="button" onClick={onOpenChunks}>
          <b>{current?.chunk_count || 0}</b>
          <span>片段</span>
        </button>
      </div>
      {canEdit && (
        <div className="document-actions">
          <div className="document-action-toggle">
            <span>AI 引用</span>
            <button
              className={`ios-switch ${isActive ? "on" : ""}`}
              type="button"
              role="switch"
              aria-checked={isActive}
              aria-label={`${isActive ? "停用" : "启用"}${document.title}`}
              onClick={() => onToggle(document.id)}
            >
              <span />
            </button>
          </div>
          <div className="document-action-buttons">
            <button className={`doc-action-button ${isEditing ? "is-active" : ""}`} type="button" onClick={() => setIsEditing((value) => !value)}>{isEditing ? "收起" : "编辑"}</button>
            <button className="doc-action-button danger" type="button" onClick={onDelete}>删除</button>
          </div>
        </div>
      )}
      {canEdit && isEditing && (
        <div className="document-edit-panel">
          <div className="document-edit-group">
            <div className="edit-group-title">
              <span>文件信息</span>
              <small>用于列表名称和引用来源</small>
            </div>
            <label>
              <span>文件名</span>
              <input value={editForm.title} onChange={(event) => setEditForm({ ...editForm, title: event.target.value })} />
            </label>
            <label className="document-reparse-toggle">
              <input type="checkbox" checked={editForm.reparse} onChange={(event) => setEditForm({ ...editForm, reparse: event.target.checked })} />
              <span>保存后重新解析文件</span>
            </label>
          </div>
          <div className="document-edit-group document-edit-settings">
            <div className="edit-group-title">
              <span>资料设置</span>
              <small>影响检索、解析和 AI 引用</small>
            </div>
            <div className="document-edit-row">
              <span>资料类型</span>
              <div className="edit-type-toggle">
                {documentTypeOptions.map((item) => (
                  <button
                    key={item}
                    type="button"
                    className={editForm.source_type === item ? "active" : ""}
                    onClick={() => setEditForm({ ...editForm, source_type: item, tags: "" })}
                  >
                    {item}
                  </button>
                ))}
              </div>
            </div>
            <div className="document-edit-row">
              <span>标签设置</span>
              <div className="edit-tag-row">
                {editTagPresets.map((tag) => (
                  <button
                    key={tag}
                    type="button"
                    className={editTags.includes(tag) ? "selected" : ""}
                    onClick={() => setEditForm({ ...editForm, tags: toggleDocumentTag(editForm.tags, tag) })}
                  >
                    {tag}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <div className="document-edit-actions">
            <div className="edit-save-note">
              <span>保存设置</span>
              <p>{editForm.reparse ? "会重新解析当前文件，并更新后续 AI 引用。" : "仅更新文件名、类型和标签，不重新拆分片段。"}</p>
            </div>
            <div className="edit-save-buttons">
              <button className="edit-save-button is-ghost" type="button" disabled={isSaving} onClick={() => setIsEditing(false)}>取消</button>
              <button className="edit-save-button is-primary" type="button" disabled={isSaving || !editForm.title.trim()} onClick={submitEdit}>{isSaving ? "保存中" : "保存"}</button>
            </div>
          </div>
        </div>
      )}
    </article>
  );
}

function ChunkDetail({ document, onBack, onError }) {
  const [chunks, setChunks] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [filters, setFilters] = useState({ chunk_type: "", stage: "", scenario: "", status: "" });
  const [loading, setLoading] = useState(false);
  const typeOptions = Object.keys(document.current_version?.structured_data?.chunk_types || {});
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  useEffect(() => {
    setPage(1);
  }, [pageSize, filters.chunk_type, filters.stage, filters.scenario, filters.status]);

  useEffect(() => {
    loadChunks().catch((err) => onError(err.message));
  }, [document.id, page, pageSize, filters.chunk_type, filters.stage, filters.scenario, filters.status]);

  async function loadChunks() {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
      Object.entries(filters).forEach(([key, value]) => {
        if (value) params.set(key, value);
      });
      const data = await api(`/knowledge/documents/${document.id}/chunks?${params.toString()}`);
      setChunks(data.items || []);
      setTotal(data.total || 0);
    } finally {
      setLoading(false);
    }
  }

  function updateFilter(key, value) {
    setFilters((prev) => ({ ...prev, [key]: value }));
  }

  return (
    <section className="page chunk-detail-page">
      <div className="hero">
        <div className="intro">
          <button className="text-button back-button" onClick={onBack}>返回文档列表</button>
          <span className="eyebrow">片段详情</span>
          <h3>{document.title}</h3>
          <p className="hint">{document.parse_summary || "用于检查文档解析质量；片段只有启用后才会参与陪练和复盘引用。"}</p>
        </div>
        <div className="metric-card">
          <span className="small">当前版本</span>
          <strong>{document.current_version?.version_label || "-"}</strong>
          <p className="small">{total} 个片段</p>
        </div>
      </div>
      <section className="panel chunk-detail-panel">
        <div className="panel-inner">
          <div className="chunk-controls">
            <label>片段类型<select value={filters.chunk_type} onChange={(e) => updateFilter("chunk_type", e.target.value)}><option value="">全部类型</option>{typeOptions.map((item) => <option key={item}>{item}</option>)}</select></label>
            <label>商机阶段<select value={filters.stage} onChange={(e) => updateFilter("stage", e.target.value)}>{chunkStageOptions.map((item) => <option key={item} value={item}>{item || "全部阶段"}</option>)}</select></label>
            <label>场景<select value={filters.scenario} onChange={(e) => updateFilter("scenario", e.target.value)}>{chunkScenarioOptions.map((item) => <option key={item || "all"} value={item}>{item || "全部场景"}</option>)}</select></label>
            <label>状态<select value={filters.status} onChange={(e) => updateFilter("status", e.target.value)}><option value="">全部状态</option><option value="active">启用</option><option value="disabled">停用</option></select></label>
            <div className="page-size-switch">
              <span>每页</span>
              {documentPageSizes.map((size) => <button key={size} className={pageSize === size ? "active" : ""} type="button" onClick={() => setPageSize(size)}>{size}</button>)}
            </div>
          </div>
          <div className="chunk-list">
            {loading ? <div className="empty-card">正在加载片段...</div> : chunks.map((chunk) => (
              <article className="chunk-card" key={chunk.id}>
                <div className="chunk-card-head">
                  <div>
                    <b>{chunk.title}</b>
                    <div className="mini-line">
                      <span>{chunk.chunk_type}</span>
                      <span>{chunk.stage}</span>
                      <span>{chunk.scenario}</span>
                      <span>{chunk.section_title || "未标注章节"}</span>
                    </div>
                  </div>
                  <div className="chunk-meta">
                    <span>{chunk.page_start ? `第 ${chunk.page_start}${chunk.page_end && chunk.page_end !== chunk.page_start ? `-${chunk.page_end}` : ""} 页` : "无页码"}</span>
                    <em>{chunk.confidence}%</em>
                    <i className={chunk.status === "active" ? "active" : ""}>{chunk.status === "active" ? "启用" : "停用"}</i>
                  </div>
                </div>
                <p>{chunk.content}</p>
              </article>
            ))}
            {!loading && !chunks.length && <div className="empty-card">当前筛选下没有片段。</div>}
          </div>
          <div className="pagination-bar">
            <span>当前 {total ? (page - 1) * pageSize + 1 : 0}-{Math.min(page * pageSize, total)} / {total} 条</span>
            <div className="pagination-controls">
              <button className="secondary" disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>上一页</button>
              <span className="small">第 {page} / {totalPages} 页</span>
              <button className="secondary" disabled={page >= totalPages} onClick={() => setPage((value) => Math.min(totalPages, value + 1))}>下一页</button>
            </div>
          </div>
        </div>
      </section>
    </section>
  );
}

function splitDocumentTags(value) {
  return (value || "")
    .split(/[、,，\s]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function toggleDocumentTag(value, tag) {
  const tags = splitDocumentTags(value);
  const nextTags = tags.includes(tag) ? tags.filter((item) => item !== tag) : [...tags, tag];
  return nextTags.join("、");
}

function fileExtensionLabel(file) {
  const ext = file?.name?.split(".").pop();
  return ext ? ext.toUpperCase() : "FILE";
}

function fileSizeLabel(size = 0) {
  if (!size) return "0 KB";
  if (size < 1024 * 1024) return `${Math.max(1, Math.round(size / 1024))} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function analysisStatusText(status) {
  return {
    analyzing: "正在分析内容",
    ready: "已完成预分析",
    error: "已使用本地规则预选",
    idle: "等待选择文件",
  }[status] || "等待选择文件";
}

function analysisStatusTitle(status) {
  return {
    analyzing: "LLM 预分析中",
    ready: "预分析完成",
    error: "预分析兜底",
    idle: "等待文件",
  }[status] || "等待文件";
}

async function readDocumentPreview(file) {
  if (!file) return "";
  const lowerName = file.name.toLowerCase();
  const isTextLike = file.type.startsWith("text/") || lowerName.endsWith(".txt") || lowerName.endsWith(".md");
  if (!isTextLike) return "";
  try {
    return (await file.text()).slice(0, 8000);
  } catch {
    return "";
  }
}

function inferDocumentSourceType(file, fallback, preview = "") {
  const text = `${file?.name || ""} ${preview}`.toLowerCase();
  if (/(说明书|产品|参数|工艺|使用方法|application|spec|manual)/i.test(text)) return "产品说明书";
  if (/(sop|话术|销售流程|商务谈判|评分标准|禁用话术|异议处理)/i.test(text)) return "SOP 与话术";
  return fallback || documentUploadDefaults.source_type;
}

function inferDocumentTags(file, sourceType, preview = "") {
  const presets = documentTagPresets[sourceType] || [];
  const text = `${file?.name || ""} ${preview}`.toLowerCase();
  const matched = presets.filter((tag) => (documentTagKeywords[tag] || []).some((keyword) => text.includes(keyword.toLowerCase())));
  if (matched.length) return matched.slice(0, 5);
  return sourceType === "产品说明书" ? ["产品参数", "应用场景"] : ["销售流程", "推荐话术"];
}

function parseStatusLabel(status) {
  return {
    parsed: "已解析",
    pending: "解析中",
    empty: "无有效正文",
    quality_low: "解析质量不足",
    failed: "解析失败",
  }[status] || status || "未知";
}

function buildTrainingPayload(form) {
  const lines = [
    form.background,
    `业务员：${form.owner_name}`,
    `产品：${form.product_name}`,
    `需求：${form.product_need}`,
  ];
  if (form.training_type === OPPORTUNITY_MODE) {
    lines.push(`最近一次沟通结果：${form.last_contact}`);
    lines.push(`关键阻碍：${form.decision_blocker}`);
    lines.push(`下一步里程碑：${form.next_milestone}`);
    lines.push(`关键人参与情况：${form.stakeholder}`);
  }
  return {
    training_type: form.training_type,
    stage: form.stage,
    goal: form.goal,
    customer_name: form.customer_name,
    customer_type: form.customer_type,
    customer_difficulty: form.customer_difficulty,
    customer_personality: form.customer_personality,
    customer_concern: form.customer_concern,
    template_id: form.template_id,
    setup_context: buildSetupContext(form),
    background: lines.filter(Boolean).join("\n"),
  };
}

function buildSetupContext(form) {
  const base = {
    guide_flow: form.training_type === OPPORTUNITY_MODE ? "opportunity_coach" : "scenario_coaching",
    customer_info: {
      owner_name: form.owner_name,
      customer_name: form.customer_name,
      customer_type: form.customer_type,
      product_name: form.product_name,
      product_need: form.product_need,
    },
    training_profile: {
      stage: form.stage,
      goal: form.goal,
      customer_difficulty: form.customer_difficulty,
      customer_personality: form.customer_personality,
      customer_concern: form.customer_concern,
      template_id: form.template_id,
      background: form.background,
    },
  };
  if (form.training_type !== OPPORTUNITY_MODE) {
    return {
      ...base,
      scenario_setup: {
        scenario: form.goal,
        objection_type: form.customer_concern,
      },
    };
  }
  return {
    ...base,
    opportunity_setup: {
      last_contact: form.last_contact,
      decision_blocker: form.decision_blocker,
      next_milestone: form.next_milestone,
      stakeholder: form.stakeholder,
    },
  };
}

function sessionPayloadFromSession(item) {
  return {
    training_type: item.training_type,
    stage: item.stage,
    goal: item.goal,
    customer_name: item.customer_name,
    customer_type: item.customer_type,
    customer_difficulty: item.customer_difficulty || "标准",
    customer_personality: item.customer_personality || "谨慎型",
    customer_concern: item.customer_concern || "价格",
    template_id: item.template_id || "",
    setup_context: item.setup_context || {},
    background: item.background,
  };
}

function withSessionMeta(report, item, formContext) {
  if (!report || !item) return report;
  const base = {
    ...report,
    training_type: item.training_type,
    stage: item.stage,
    goal: item.goal,
    conversation_review: buildConversationReview(report, item),
  };
  if (item.training_type !== OPPORTUNITY_MODE) return base;
  const opportunityContext = opportunityContextFromSession(item, formContext);
  return {
    ...base,
    opportunity_context: opportunityContext,
    opportunity_diagnosis: buildOpportunityDiagnosis(item, opportunityContext),
  };
}

function buildConversationReview(report, item) {
  const salesMessages = (item.messages || []).filter((msg) => msg.role === "sales").map((msg) => msg.content).filter(Boolean);
  const quote = salesMessages.find((text) => text.length >= 18) || salesMessages[0] || "本轮对话还缺少可沉淀的话术表达。";
  const strongScore = [...(report.scores || [])].sort((a, b) => b.value - a.value)[0];
  const weakScore = [...(report.scores || [])].sort((a, b) => a.value - b.value)[0];
  return {
    highlights: [
      strongScore ? `${strongScore.name}表现相对突出：${strongScore.reason}` : "本轮能围绕客户问题持续回应，没有过早结束沟通。",
      "业务员能够承接客户异议，并尝试把话题推进到下一步动作。",
    ],
    quotes: [`“${quote}”`],
    analysis: [
      weakScore ? `${weakScore.name}仍需加强：${weakScore.reason}` : "需要继续提升追问深度，把客户的模糊反馈拆成可确认事项。",
      (report.alternatives || [])[0] || "下一轮建议把问题收敛到时间、人员、资料或测试条件中的一个明确动作。",
    ],
  };
}

function opportunityContextFromSession(item, formContext) {
  const fromBackground = extractOpportunityContext(item.background || "");
  const context = item.setup_context?.opportunity_setup || {};
  return {
    customer_name: formContext?.customer_name || item.customer_name,
    stage: formContext?.stage || item.stage,
    goal: formContext?.goal || item.goal,
    last_contact: formContext?.last_contact || context.last_contact || fromBackground.last_contact || "最近一次沟通结果还不清晰",
    decision_blocker: formContext?.decision_blocker || context.decision_blocker || fromBackground.decision_blocker || "关键人未参与",
    next_milestone: formContext?.next_milestone || context.next_milestone || fromBackground.next_milestone || "约到关键人会议",
    stakeholder: formContext?.stakeholder || context.stakeholder || fromBackground.stakeholder || "至少确认采购、技术和老板谁有最终影响力",
  };
}

function extractOpportunityContext(background) {
  const keys = {
    last_contact: "最近一次沟通结果",
    decision_blocker: "关键阻碍",
    next_milestone: "下一步里程碑",
    stakeholder: "关键人参与情况",
  };
  return Object.fromEntries(Object.entries(keys).map(([key, label]) => {
    const match = background.match(new RegExp(`${label}：([^\\n]+)`));
    return [key, match?.[1]?.trim() || ""];
  }));
}

function buildOpportunityDiagnosis(item, context) {
  const stageRiskMap = {
    了解商机: "线索质量和首次接触不明确，容易停留在泛泛沟通。",
    确认商机: "真实需求、样品和关键人尚未完全确认，商机容易空转。",
    方案论证: "测试证据和客户试样反馈不足，方案认可点可能不清晰。",
    商务谈判: "价格、账期、交付和服务条件未收口，客户容易继续压价。",
    销售成交: "合同、订单交付和责任边界若不明确，成交会反复拖延。",
    回款: "账期压力和复购节奏未拆开，容易影响现金流和长期合作。",
  };
  const riskMap = {
    关键人未参与: "当前最大风险是决策链不完整，单靠采购沟通容易被卡在内部评估。",
    价格未达预期: "当前最大风险是客户把谈判压缩为单价比较，忽略稳定性、返修和交付成本。",
    样品或测试未完成: "当前最大风险是缺少可验证证据，客户很难承担替换风险。",
    账期或付款压力: "当前最大风险是回款和继续供货混在一起，关系维护与账期风险都不清晰。",
    竞品正在替代: "当前最大风险是客户已经进入替代评估，但真实评价标准没有被掌握。",
  };
  const stage = context.stage || item.stage;
  return {
    judgment: `${context.customer_name || item.customer_name} 当前处于“${stage}”阶段，重点不是继续补充介绍，而是确认 ${context.next_milestone}。`,
    stageRisk: stageRiskMap[stage] || "当前阶段需要先确认客户真实卡点，再把动作收敛到一个明确节点。",
    keyRisk: riskMap[context.decision_blocker] || `当前最大风险是“${context.decision_blocker}”没有被拆成可推进动作。`,
    keyPeople: context.stakeholder || "至少确认采购、技术和老板谁有最终影响力",
    negotiationStrategy: `基于最近沟通结果“${context.last_contact}”，下一次沟通要先复述客户卡点，再围绕“${context.decision_blocker}”确认责任人、时间点和判断标准。`,
    nextActions: [
      `把下一步收敛为“${context.next_milestone}”，不要只说保持沟通。`,
      `围绕“${context.decision_blocker}”设计一个具体问题，确认客户内部卡点。`,
      `补齐关键人：${context.stakeholder || "至少确认采购、技术和老板谁有最终影响力"}。`,
      "把时间、人员、资料或测试条件写成一个明确的跟进动作。",
    ],
  };
}

function normalizeTextList(value) {
  if (!Array.isArray(value)) return [];
  return value.map((item) => {
    if (typeof item === "string") return item;
    if (item && typeof item === "object") return item.text || item.detail || item.reason || item.content || item.title || "";
    return "";
  }).filter(Boolean);
}

function normalizeStrategies(value) {
  const defaults = [
    { title: "卡点复述", text: "下一次沟通先复述客户卡点，再确认责任人、时间点和判断标准。" },
    { title: "关键人推进", text: "不要只跟单一联系人沟通，先确认采购、技术和最终决策人分别关心什么。" },
    { title: "条件换承诺", text: "把补资料、试样或价格条件绑定到客户明确承诺上。" },
  ];
  const items = Array.isArray(value) ? value : [];
  return defaults.map((fallback, index) => {
    const item = items[index];
    if (typeof item === "string") return { ...fallback, text: item };
    if (item && typeof item === "object") {
      return {
        title: item.title || item.name || fallback.title,
        text: item.text || item.detail || item.content || item.strategy || fallback.text,
      };
    }
    return fallback;
  });
}

function normalizeTodos(checklist, alternatives) {
  const titles = ["确认下一步节点", "拆解关键阻碍", "补齐关键人", "固化跟进动作"];
  const dues = ["1 天内", "2 天内", "3 天内", "5 天内"];
  const altTexts = normalizeTextList(alternatives);
  const items = Array.isArray(checklist) ? checklist : [];
  return titles.map((fallbackTitle, index) => {
    const item = items[index];
    if (typeof item === "string") {
      return { title: fallbackTitle, detail: item, due: dues[index] };
    }
    if (item && typeof item === "object") {
      return {
        title: item.title || item.name || fallbackTitle,
        detail: item.detail || item.content || item.task || item.text || altTexts[index] || "把当前问题拆成一个可执行动作。",
        due: item.due || item.deadline || item.time || dues[index],
      };
    }
    return {
      title: fallbackTitle,
      detail: altTexts[index] || "把当前问题拆成一个可执行动作。",
      due: dues[index],
    };
  });
}

function buildSpeechPair(report, review) {
  const quote = review?.quotes?.[0] || "";
  const original = quote.replace(/[“”"]/g, "").trim() || normalizeTextList(report.risk_lines)[0] || "本轮原话术沉淀不足，建议下一轮把关键回应说完整。";
  const suggested = normalizeTextList(report.alternatives)[0] || "建议把话术收敛到一个明确的下一步动作。";
  return { original, suggested };
}

function scoreToneClass(value) {
  const score = Number(value) || 0;
  if (score <= 1) return "score-one";
  if (score === 2) return "score-two";
  if (score === 3) return "score-three";
  if (score === 4) return "score-four";
  return "score-five";
}

function trendScoreColor(value) {
  const score = Number(value) || 0;
  if (score < 40) return "#ea4335";
  if (score < 60) return "#f97316";
  if (score < 75) return "#fbbc04";
  if (score < 85) return "#34a853";
  return "#188038";
}

function buildScoreTrend(values) {
  const width = 320;
  const height = 164;
  const paddingX = 22;
  const top = 18;
  const bottom = 28;
  const safeValues = values
    .map((value) => Math.max(0, Math.min(100, Math.round(Number(value) || 0))))
    .filter((value) => Number.isFinite(value));
  const chartHeight = height - top - bottom;
  const step = safeValues.length > 1 ? (width - paddingX * 2) / (safeValues.length - 1) : 0;
  const points = safeValues.map((value, index) => ({
    index: index + 1,
    value,
    x: paddingX + step * index,
    y: top + ((100 - value) / 100) * chartHeight,
  }));
  const linePath = points.map((point, index) => `${index ? "L" : "M"} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(" ");
  const lastPoint = points[points.length - 1];
  const firstPoint = points[0];
  const baseY = height - bottom;
  const areaPath = points.length ? `${linePath} L ${lastPoint.x.toFixed(1)} ${baseY} L ${firstPoint.x.toFixed(1)} ${baseY} Z` : "";
  const gridLines = [25, 50, 75].map((score) => ({
    score,
    y: top + ((100 - score) / 100) * chartHeight,
  }));
  return { width, height, paddingX, points, linePath, areaPath, gridLines };
}

function scoreLevelLabel(value) {
  const score = Number(value) || 0;
  if (score <= 1) return "严重短板";
  if (score === 2) return "需补强";
  if (score === 3) return "可巩固";
  if (score === 4) return "表现稳定";
  return "优势项";
}

const SCORE_DIMENSION_ORDER = ["SOP执行", "客户洞察", "需求澄清", "异议处理", "价值表达", "推进动作", "话术质量"];

function normalizeDashboardScores(items) {
  const source = Array.isArray(items) ? items : [];
  const byName = new Map(source.map((item) => [item.name, { ...item, value: Number(item.value) || 0 }]));
  return SCORE_DIMENSION_ORDER.map((name) => byName.get(name) || { name, value: 0, count: 0 });
}

function cleanDashboardLabel(value) {
  const text = String(value || "").trim();
  if (!text || /^\?+$/.test(text)) return "";
  if (/urgent|competitor|discount|objection/i.test(text)) return "价格异议";
  if (text.length > 18) return `${text.slice(0, 18)}...`;
  return text;
}

function distributionRows(distribution, limit = 5) {
  const bucket = new Map();
  Object.entries(distribution || {}).forEach(([rawName, rawValue]) => {
    const name = cleanDashboardLabel(rawName);
    if (!name) return;
    const value = Number(rawValue) || 0;
    bucket.set(name, (bucket.get(name) || 0) + value);
  });
  const rows = [...bucket.entries()]
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value);
  const total = rows.reduce((sum, item) => sum + item.value, 0) || 1;
  const top = rows.slice(0, limit).map((item) => ({ ...item, percent: Math.round((item.value / total) * 100) }));
  const rest = rows.slice(limit).reduce((sum, item) => sum + item.value, 0);
  if (rest) top.push({ name: "其他", value: rest, percent: Math.round((rest / total) * 100) });
  return top;
}

function DistributionRow({ item }) {
  return (
    <div className="distribution-row">
      <span>{item.name}</span>
      <i style={{ "--value": `${item.percent}%` }}><b /></i>
      <em>{item.value}</em>
    </div>
  );
}

function cleanTaskText(text) {
  const cleaned = String(text || "")
    .replace(/^下一轮训练[:：]\s*/, "")
    .replace(/^下一轮(?:先)?(?:增加|补充|重点)?(?:演练|练习|训练)[:：]?\s*/, "")
    .replace(/^训练[:：]\s*/, "")
    .trim();
  return cleaned;
}

function compactTaskLabel(text) {
  const cleaned = cleanTaskText(text);
  const quoted = cleaned.match(/[“"‘']([^”"’']{2,10})[”"’']/);
  if (quoted) return quoted[1];
  if (/价值表达|色牢度|返修|稳定性|总成本|成本/.test(cleaned)) return "价值表达补强";
  if (/邮件|只接收邮件|发邮件/.test(cleaned)) return "邮件沟通推进";
  if (/关键人/.test(cleaned)) return "关键人扩展推进";
  if (/承诺|条件交换|换承诺/.test(cleaned)) return "条件换承诺";
  if (/价格|报价|降价/.test(cleaned) && /异议|压价|敏感/.test(cleaned)) return "价格异议确认";
  if (/时间|条件|节点/.test(cleaned)) return "推进条件确认";
  if (/需求|工艺|测试/.test(cleaned)) return "需求测试澄清";
  if (/异议|拒绝|反对|担心/.test(cleaned)) return "异议回应练习";
  if (cleaned.length <= 10) return cleaned;
  return `${cleaned.slice(0, 8)}...`;
}

function buildTrainingTask(text, index) {
  const detail = cleanTaskText(text);
  const title = compactTaskLabel(text);
  const purpose = trainingTaskPurpose(detail, title);
  const due = trainingTaskDue(detail, index);
  return { title, purpose, due, detail };
}

function trainingTaskPurpose(detail, title) {
  if (/价值表达|色牢度|返修|稳定性|总成本|成本/.test(detail + title)) return "把产品价值说清楚，避免只停留在价格比较。";
  if (/邮件|只接收邮件|发邮件/.test(detail + title)) return "客户不愿见面时，也能把下一步动作推进下去。";
  if (/关键人/.test(detail + title)) return "找到真实决策链，减少单点沟通造成的停滞。";
  if (/价格|报价|降价|压价/.test(detail + title)) return "先确认异议来源，再判断是否需要谈条件。";
  if (/时间|条件|节点|承诺/.test(detail + title)) return "把模糊沟通收敛成明确的人、时间和条件。";
  if (/需求|工艺|测试/.test(detail + title)) return "补齐客户判断标准，让方案论证更有依据。";
  if (/异议|拒绝|反对|担心/.test(detail + title)) return "承接客户顾虑，并转成可继续推进的问题。";
  return "把本轮短板转成下一次可练习、可复盘的开口动作。";
}

function trainingTaskDue(detail, index) {
  if (/时间|节点|关键人|推进|邮件/.test(detail)) return "1 天内";
  if (/价格|报价|异议|价值|成本/.test(detail)) return "2 天内";
  if (/工艺|测试|色牢度|方案/.test(detail)) return "3 天内";
  return `${Math.min(index + 1, 3)} 天内`;
}

function input(label, key, form, setForm) {
  return <label>{label}<input value={form[key]} onChange={(e) => setForm({ ...form, [key]: e.target.value })} /></label>;
}

function select(label, key, form, setForm, options) {
  return <label>{label}<select value={form[key]} onChange={(e) => setForm({ ...form, [key]: e.target.value })}>{options.map((item) => <option key={item}>{item}</option>)}</select></label>;
}

function Card({ title, children, className = "" }) {
  return <section className={`card ${className}`.trim()}><h3>{title}</h3>{children}</section>;
}

function AbilityRadar({ scores }) {
  const items = (scores || []).slice(0, 7);
  const [activeIndex, setActiveIndex] = useState(null);
  if (!items.length) return <div className="radar-empty">暂无评分维度</div>;
  const center = 118;
  const maxRadius = 84;
  const axis = items.map((item, index) => {
    const angle = (Math.PI * 2 * index) / items.length - Math.PI / 2;
    const valueRadius = maxRadius * Math.max(0, Math.min(5, item.value)) / 5;
    return {
      ...item,
      labelX: center + Math.cos(angle) * (maxRadius + 10),
      labelY: center + Math.sin(angle) * (maxRadius + 10),
      endX: center + Math.cos(angle) * maxRadius,
      endY: center + Math.sin(angle) * maxRadius,
      pointX: center + Math.cos(angle) * valueRadius,
      pointY: center + Math.sin(angle) * valueRadius,
    };
  });
  const polygon = axis.map((item) => `${item.pointX},${item.pointY}`).join(" ");
  const rings = [1, 2, 3, 4, 5].map((level) => {
    const radius = maxRadius * level / 5;
    return axis.map((_, index) => {
      const angle = (Math.PI * 2 * index) / items.length - Math.PI / 2;
      return `${center + Math.cos(angle) * radius},${center + Math.sin(angle) * radius}`;
    }).join(" ");
  });
  const activeItem = activeIndex === null ? null : axis[activeIndex];
  return (
    <div className="radar-wrap">
      <div className="radar-figure">
        <svg className="radar-chart" viewBox="0 0 236 236" role="img" aria-label="能力雷达图">
          {rings.map((points, index) => <polygon key={index} points={points} className="radar-ring" />)}
          {axis.map((item) => <line key={item.name} x1={center} y1={center} x2={item.endX} y2={item.endY} className="radar-axis" />)}
          <polygon points={polygon} className="radar-area" />
          <polyline points={`${polygon} ${axis[0].pointX},${axis[0].pointY}`} className="radar-line" />
          {axis.map((item, index) => (
            <g
              key={item.name}
              className="radar-point"
              role="button"
              tabIndex="0"
              aria-label={`${item.name} ${item.value}分`}
              onMouseEnter={() => setActiveIndex(index)}
              onMouseLeave={() => setActiveIndex(null)}
              onFocus={() => setActiveIndex(index)}
              onBlur={() => setActiveIndex(null)}
              onClick={() => setActiveIndex(activeIndex === index ? null : index)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  setActiveIndex(activeIndex === index ? null : index);
                }
              }}
            >
              <circle cx={item.pointX} cy={item.pointY} r="12" className="radar-hit" />
              <circle cx={item.pointX} cy={item.pointY} r="4" className={`radar-dot ${activeIndex === index ? "active" : ""}`} />
            </g>
          ))}
        </svg>
        {axis.map((item) => (
          <span
            className={`radar-label ${activeItem?.name === item.name ? "active" : ""}`}
            key={item.name}
            style={{
              left: `${(item.labelX / 236) * 100}%`,
              top: `${(item.labelY / 236) * 100}%`,
              transform: "translate(-50%, -50%)",
            }}
          >
            {item.name}
          </span>
        ))}
        {activeItem && (
          <div
            className="radar-tooltip"
            style={{
              left: `${(activeItem.pointX / 236) * 100}%`,
              top: `${(activeItem.pointY / 236) * 100}%`,
            }}
          >
            <b>{activeItem.name}</b>
            <span>{activeItem.value} 分</span>
          </div>
        )}
      </div>
    </div>
  );
}

function Empty({ title, text }) {
  return <section className="empty"><h2>{title}</h2><p>{text}</p></section>;
}

function formatDate(value) {
  return new Date(value).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function goalIcon(id) {
  const icons = {
    price: <><path d="M5 12h14"></path><path d="M8 8h8"></path><path d="M8 16h5"></path></>,
    stalled: <><path d="M5 12h8"></path><path d="M13 7l5 5-5 5"></path><path d="M5 6h5"></path><path d="M5 18h5"></path></>,
    technical: <><path d="M9 4h6"></path><path d="M10 4v5l-4 7a3 3 0 0 0 2.6 4.5h6.8A3 3 0 0 0 18 16l-4-7V4"></path><path d="M8 15h8"></path></>,
    payment: <><path d="M4 7h16v10H4z"></path><path d="M4 10h16"></path><path d="M8 15h4"></path></>,
    retention: <><path d="M7 8a5 5 0 0 1 8.5-2.8L18 7"></path><path d="M18 4v3h-3"></path><path d="M17 16a5 5 0 0 1-8.5 2.8L6 17"></path><path d="M6 20v-3h3"></path></>,
    lead: <><path d="M5 19l5-5"></path><path d="M14 4l6 6-8 8H6v-6z"></path><path d="M15 9l-6 6"></path></>,
    visit: <><path d="M12 21s7-5.2 7-11a7 7 0 0 0-14 0c0 5.8 7 11 7 11z"></path><path d="M12 10h.01"></path></>,
    sample: <><path d="M8 4h8"></path><path d="M9 4v5l-3 8a3 3 0 0 0 2.8 4h6.4A3 3 0 0 0 18 17l-3-8V4"></path><path d="M8 15h8"></path></>,
    stakeholder: <><path d="M8 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6z"></path><path d="M3.5 19a4.5 4.5 0 0 1 9 0"></path><path d="M17 9a2.5 2.5 0 1 0 0-5"></path><path d="M15 19h5"></path></>,
    trial: <><path d="M5 5h14v14H5z"></path><path d="M8 12l2.5 2.5L16 9"></path></>,
    report: <><path d="M6 4h9l3 3v13H6z"></path><path d="M14 4v4h4"></path><path d="M9 13h6"></path><path d="M9 17h4"></path></>,
    contract: <><path d="M7 4h10v16H7z"></path><path d="M10 8h4"></path><path d="M10 12h4"></path><path d="M10 16h2"></path></>,
    delivery: <><path d="M4 7h10v8H4z"></path><path d="M14 10h3l3 3v2h-6z"></path><path d="M7 18h.01"></path><path d="M17 18h.01"></path></>,
    service: <><path d="M12 3l7 4v5c0 4-3 7-7 9-4-2-7-5-7-9V7z"></path><path d="M9 12l2 2 4-5"></path></>,
  };
  return <svg viewBox="0 0 24 24" aria-hidden="true">{icons[id] || icons.price}</svg>;
}

function navIcon(id) {
  const icons = {
    start: <><path d="M4 7h16"></path><path d="M4 12h16"></path><path d="M4 17h10"></path></>,
    chat: <><path d="M5 6h14v9H9l-4 4z"></path><path d="M8 9h8"></path></>,
    report: <><path d="M5 19V5"></path><path d="M5 19h14"></path><path d="M9 15v-4"></path><path d="M13 15V8"></path><path d="M17 15v-6"></path></>,
    history: <><path d="M5 5h14v14H5z"></path><path d="M8 9h8"></path><path d="M8 13h5"></path></>,
    dashboard: <><path d="M4 13h6V5H4z"></path><path d="M14 19h6V5h-6z"></path><path d="M4 19h6v-3H4z"></path></>,
    knowledge: <><path d="M6 4h9l3 3v13H6z"></path><path d="M14 4v4h4"></path><path d="M9 12h6"></path><path d="M9 16h6"></path></>,
  };
  return <svg viewBox="0 0 24 24" aria-hidden="true">{icons[id]}</svg>;
}

createRoot(document.getElementById("root")).render(<App />);
