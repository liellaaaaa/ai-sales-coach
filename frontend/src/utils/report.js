import { OPPORTUNITY_MODE } from "../constants/training";

export function withSessionMeta(report, item, formContext) {
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

export function buildConversationReview(report, item) {
  const salesMessages = (item.messages || []).filter((msg) => msg.role === "sales").map((msg) => msg.content).filter(Boolean);
  const quote = salesMessages.find((text) => text.length >= 18) || salesMessages[0] || "本轮对话还缺少可沉淀的话术表达。";
  const strongScore = [...(report.scores || [])].sort((a, b) => b.value - a.value)[0];
  const weakScore = [...(report.scores || [])].sort((a, b) => a.value - b.value)[0];
  return {
    highlights: [
      strongScore ? `${strongScore.name}表现相对突出：${strongScore.reason}` : "本轮能围绕客户问题持续回应，没有过早结束沟通。",
      "业务员能够承接客户异议，并尝试把话题推进到下一步动作。",
    ],
    quotes: [`"${quote}"`],
    analysis: [
      weakScore ? `${weakScore.name}仍需加强：${weakScore.reason}` : "需要继续提升追问深度，把客户的模糊反馈拆成可确认事项。",
      (report.alternatives || [])[0] || "下一轮建议把问题收敛到时间、人员、资料或测试条件中的一个明确动作。",
    ],
  };
}

export function opportunityContextFromSession(item, formContext) {
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

export function extractOpportunityContext(background) {
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

export function buildOpportunityDiagnosis(item, context) {
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
    judgment: `${context.customer_name || item.customer_name} 当前处于"${stage}"阶段，重点不是继续补充介绍，而是确认 ${context.next_milestone}。`,
    stageRisk: stageRiskMap[stage] || "当前阶段需要先确认客户真实卡点，再把动作收敛到一个明确节点。",
    keyRisk: riskMap[context.decision_blocker] || `当前最大风险是"${context.decision_blocker}"没有被拆成可推进动作。`,
    keyPeople: context.stakeholder || "至少确认采购、技术和老板谁有最终影响力",
    negotiationStrategy: `基于最近沟通结果"${context.last_contact}"，下一次沟通要先复述客户卡点，再围绕"${context.decision_blocker}"确认责任人、时间点和判断标准。`,
    nextActions: [
      `把下一步收敛为"${context.next_milestone}"，不要只说保持沟通。`,
      `围绕"${context.decision_blocker}"设计一个具体问题，确认客户内部卡点。`,
      `补齐关键人：${context.stakeholder || "至少确认采购、技术和老板谁有最终影响力"}。`,
      "把时间、人员、资料或测试条件写成一个明确的跟进动作。",
    ],
  };
}

export function normalizeTextList(value) {
  if (!Array.isArray(value)) return [];
  return value.map((item) => {
    if (typeof item === "string") return item;
    if (item && typeof item === "object") return item.text || item.detail || item.reason || item.content || item.title || "";
    return "";
  }).filter(Boolean);
}

export function normalizeStrategies(value) {
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

export function normalizeTodos(checklist, alternatives) {
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

export function buildSpeechPair(report, review) {
  const quote = review?.quotes?.[0] || "";
  const original = quote.replace(/["""]/g, "").trim() || normalizeTextList(report.risk_lines)[0] || "本轮原话术沉淀不足，建议下一轮把关键回应说完整。";
  const suggested = normalizeTextList(report.alternatives)[0] || "建议把话术收敛到一个明确的下一步动作。";
  return { original, suggested };
}
