import { OPPORTUNITY_MODE, apiGoalFromDisplay } from "../constants/training";
import { extractOpportunityContext, normalizeStrategies, normalizeTodos } from "./report";

export function buildTrainingPayload(form) {
  const lines = [
    form.background,
    `业务员：${form.owner_name}`,
    `产品：${form.product_name}`,
    `需求：${form.product_need}`,
    `客户关系：${form.customer_type}`,
  ];
  if (form.customer_persona) {
    lines.push(`客户画像：${form.customer_persona}`);
  }
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

export function buildSetupContext(form) {
  const base = {
    guide_flow: form.training_type === OPPORTUNITY_MODE ? "opportunity_coach" : "scenario_coaching",
    customer_info: {
      owner_name: form.owner_name,
      customer_name: form.customer_name,
      customer_type: form.customer_type,
      customer_persona: form.customer_persona || "",
      product_name: form.product_name,
      product_need: form.product_need,
    },
    training_profile: {
      stage: form.stage,
      goal: form.goal,
      goal_api: apiGoalFromDisplay(form.goal),
      customer_relationship: form.customer_type,
      customer_persona: form.customer_persona || "",
      customer_difficulty: form.customer_difficulty,
      customer_personality: form.customer_personality,
      customer_concern: form.customer_concern,
      template_id: form.template_id,
      background: form.background,
    },
  };
  if (form.plan_training) {
    base.plan_training = form.plan_training;
  }
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

function pickText(...values) {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

function concernFromBlocker(blocker) {
  const text = String(blocker || "");
  if (/样品|测试|试样|工艺/.test(text)) return "工艺适配";
  if (/价格|报价|账期|付款/.test(text)) return "价格";
  if (/关键人|决策|竞品|替代/.test(text)) return "供应稳定";
  return "";
}

function extractLabeledLine(background, label) {
  const match = String(background || "").match(new RegExp(`${label}：([^\\n]+)`));
  return match?.[1]?.trim() || "";
}

export function buildPlanTrainingDraft(report, session, formContext) {
  const setup = session?.setup_context || formContext?.setup_context || {};
  const opportunitySetup = setup.opportunity_setup || {};
  const opportunityContext = report?.opportunity_context || {};
  const backgroundSource = session?.background || formContext?.background || "";
  const fromBackground = extractOpportunityContext(backgroundSource);

  const customer_name = pickText(
    session?.customer_name,
    opportunityContext.customer_name,
    report?.customer_name,
    formContext?.customer_name,
    "当前客户"
  );
  const stage = pickText(session?.stage, opportunityContext.stage, report?.stage, formContext?.stage);
  const goal = pickText(session?.goal, opportunityContext.goal, report?.goal, formContext?.goal);
  const product_name = pickText(
    extractLabeledLine(backgroundSource, "产品"),
    formContext?.product_name,
    setup.customer_info?.product_name
  );
  const product_need = pickText(
    formContext?.product_need,
    setup.customer_info?.product_need,
    extractLabeledLine(backgroundSource, "需求")
  );
  const customer_type = pickText(session?.customer_type, formContext?.customer_type, "潜在新客户");
  const customer_persona = pickText(
    setup.customer_info?.customer_persona,
    setup.training_profile?.customer_persona,
    formContext?.customer_persona
  );
  const last_contact = pickText(
    opportunityContext.last_contact,
    opportunitySetup.last_contact,
    formContext?.last_contact,
    fromBackground.last_contact
  );
  const decision_blocker = pickText(
    opportunityContext.decision_blocker,
    opportunitySetup.decision_blocker,
    formContext?.decision_blocker,
    fromBackground.decision_blocker,
    "关键人未参与"
  );
  const next_milestone = pickText(
    opportunityContext.next_milestone,
    opportunitySetup.next_milestone,
    formContext?.next_milestone,
    fromBackground.next_milestone
  );
  const stakeholder = pickText(
    opportunityContext.stakeholder,
    opportunitySetup.stakeholder,
    formContext?.stakeholder,
    fromBackground.stakeholder
  );
  const customer_difficulty = pickText(session?.customer_difficulty, formContext?.customer_difficulty, "标准");
  const customer_personality = pickText(session?.customer_personality, formContext?.customer_personality, "谨慎型");
  const customer_concern = pickText(
    concernFromBlocker(decision_blocker),
    session?.customer_concern,
    formContext?.customer_concern,
    "供应稳定"
  );

  const strategies = normalizeStrategies(report?.alternatives)
    .map((item) => item.text)
    .filter(Boolean)
    .slice(0, 4);
  const checklist = normalizeTodos(report?.checklist, report?.alternatives)
    .slice(0, 4)
    .map((item) => ({ title: item.title, detail: item.detail, due: item.due }));
  const primary_action = checklist[0]?.title && checklist[0]?.detail
    ? `${checklist[0].title}：${checklist[0].detail}`
    : (checklist[0]?.detail || strategies[0] || "把下一步推进动作收敛到一个明确的人员、时间和条件。");
  const must_ask = decision_blocker
    ? `针对"${decision_blocker}"，直接确认：这件事由谁判断、什么时候能给反馈、需要我们补什么材料？`
    : "直接确认：这件事由谁判断、什么时候能给反馈、需要我们补什么材料？";
  const focus_scores = [...(report?.scores || [])]
    .filter((item) => item && item.name)
    .sort((a, b) => (Number(a.value) || 0) - (Number(b.value) || 0))
    .slice(0, 3)
    .map((item) => ({ name: item.name, value: Number(item.value) || 0, reason: item.reason || "" }));
  const plan_summary = pickText(report?.summary);

  const focusLines = [
    "",
    "【本次针对推进方案的训练焦点】",
    `优先推进动作：${primary_action}`,
    `必须问清：${must_ask}`,
    `交涉策略：${strategies.map((text, index) => `${index + 1}. ${text}`).join("；")}`,
    `执行清单：${checklist.map((item, index) => `${index + 1}. ${item.title}：${item.detail}`).join("；")}`,
  ];
  const background = `${backgroundSource}${focusLines.join("\n")}`;

  const rawSessionId = session?.id ?? report?.session_id;
  const parsedSessionId = Number(rawSessionId);
  const source_session_id = rawSessionId != null && rawSessionId !== "" && Number.isFinite(parsedSessionId)
    ? parsedSessionId
    : null;

  return {
    training_type: "客户情景陪练",
    stage,
    goal,
    customer_name,
    customer_type,
    customer_persona,
    product_name,
    product_need,
    background,
    last_contact,
    decision_blocker,
    next_milestone,
    stakeholder,
    customer_difficulty,
    customer_personality,
    customer_concern,
    template_id: "from-opportunity-plan",
    owner_name: "",
    plan_training: {
      source_session_id,
      plan_summary,
      primary_action,
      must_ask,
      strategies,
      checklist,
      focus_scores,
    },
  };
}

export function sessionPayloadFromSession(item) {
  const setup = item.setup_context || {};
  return {
    training_type: item.training_type,
    stage: item.stage,
    goal: item.goal,
    customer_name: item.customer_name,
    customer_type: item.customer_type,
    customer_difficulty: item.customer_difficulty || "标准",
    customer_personality: item.customer_personality || "谨慎型",
    customer_concern: item.customer_concern || "供应稳定",
    template_id: item.template_id || "",
    setup_context: setup,
    background: item.background,
    customer_persona: setup?.customer_info?.customer_persona || setup?.training_profile?.customer_persona || "",
  };
}
