import { OPPORTUNITY_MODE } from "../constants/training";

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
      customer_relationship: form.customer_type,
      customer_persona: form.customer_persona || "",
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
