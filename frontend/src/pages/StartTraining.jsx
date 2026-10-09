import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  OPPORTUNITY_MODE,
  opportunityStages,
  customerRelationshipOptions,
  customerPersonaOptions,
  customerDifficultyOptions,
  customerPersonalityOptions,
  customerConcernOptions,
  strongRelationshipGoals,
  getStageGoals,
  resolveGoalForStage,
  trainingTemplates,
  defaultForm,
} from "../constants/training";
import { buildTrainingPayload } from "../utils/training";
import { goalIcon } from "../components/Layout";

function mergePlanDraft(prev, draft, ownerName) {
  if (!draft) return prev;
  const stage = draft.stage || prev.stage;
  return {
    ...prev,
    ...draft,
    training_type: "客户情景陪练",
    goal: resolveGoalForStage(stage, draft.goal || prev.goal),
    owner_name: ownerName || prev.owner_name,
    plan_training: draft.plan_training,
  };
}

function emptyCustomerForm(base, ownerName) {
  return {
    ...base,
    owner_name: ownerName || base.owner_name,
    template_id: "",
    customer_name: "",
    product_name: "",
    product_need: "",
    background: "",
    last_contact: "",
    stakeholder: "",
  };
}

export default function StartTraining({ onStarted, onError, user, planDraft, onPlanDraftApplied }) {
  const ownerName = user?.name || user?.username || "";
  const [step, setStep] = useState(1);
  const [form, setForm] = useState(() => mergePlanDraft({ ...defaultForm, owner_name: ownerName }, planDraft, ownerName));
  const [formOpen, setFormOpen] = useState(false);
  const [showExtraFields, setShowExtraFields] = useState(false);
  const [relationshipTouched, setRelationshipTouched] = useState(Boolean(planDraft));
  const [isSubmitting, setIsSubmitting] = useState(false);
  const stageTabsRef = useRef(null);

  useEffect(() => {
    if (!planDraft) return;
    setForm((prev) => mergePlanDraft(prev, planDraft, ownerName));
    setRelationshipTouched(true);
    setStep(2);
    setFormOpen(true);
    onPlanDraftApplied?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [planDraft]);

  const isOpportunity = form.training_type === OPPORTUNITY_MODE;
  const stageIndex = Math.max(0, opportunityStages.findIndex((item) => item.name === form.stage));
  const activeStage = opportunityStages[stageIndex];
  const activeGoals = useMemo(() => getStageGoals(form.stage), [form.stage]);
  const visibleTemplates = trainingTemplates.filter((item) => item.training_type === form.training_type);

  function updateForm(patch) {
    setForm((prev) => ({ ...prev, ...patch }));
    onError("");
  }

  function applyRelationshipGoalSignal(goalName) {
    if (relationshipTouched) return form.customer_type;
    const cold = strongRelationshipGoals["陌拜新客户"] || [];
    const regular = strongRelationshipGoals["老客户"] || [];
    if (cold.includes(goalName)) return "陌拜新客户";
    if (regular.includes(goalName)) return "老客户";
    return form.customer_type;
  }

  function pickMode(mode) {
    updateForm({ training_type: mode, template_id: "" });
    setFormOpen(false);
    setStep(2);
  }

  function pickTemplate(template) {
    const nextStage = opportunityStages.find((stage) => stage.name === template.stage) || opportunityStages[0];
    const nextGoal = resolveGoalForStage(nextStage.name, template.goal);
    const nextRelationship = template.customer_type || applyRelationshipGoalSignal(nextGoal);
    setForm((prev) => ({
      ...prev,
      ...template,
      stage: nextStage.name,
      goal: nextGoal,
      customer_type: nextRelationship,
      template_id: template.id,
    }));
    setRelationshipTouched(Boolean(template.customer_type));
    setFormOpen(true);
    onError("");
  }

  function pickFreeForm() {
    setForm((prev) => emptyCustomerForm(prev, ownerName));
    setRelationshipTouched(false);
    setFormOpen(true);
    onError("");
  }

  function validateCustomerForm() {
    if (!form.customer_name.trim() || !form.product_name.trim() || !form.customer_type.trim() || !form.product_need.trim()) {
      return "请先补齐客户名称、产品、客户关系和需求。";
    }
    if (isOpportunity && (!form.last_contact.trim() || !form.stakeholder.trim())) {
      return "商机推进需要补充最近沟通结果和关键人参与情况。";
    }
    return "";
  }

  function goStageStep() {
    const message = validateCustomerForm();
    if (message) {
      onError(message);
      return;
    }
    onError("");
    setStep(3);
  }

  function selectStage(stage) {
    const nextGoal = resolveGoalForStage(stage.name, form.goal);
    const nextRelationship = applyRelationshipGoalSignal(nextGoal);
    setForm((prev) => ({
      ...prev,
      stage: stage.name,
      goal: nextGoal,
      customer_type: nextRelationship,
    }));
    requestAnimationFrame(() => {
      stageTabsRef.current?.querySelector(".stage-pill.active")?.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
    });
  }

  function selectGoal(goalName) {
    const nextRelationship = applyRelationshipGoalSignal(goalName);
    setForm((prev) => ({ ...prev, goal: goalName, customer_type: nextRelationship }));
  }

  function goBack() {
    onError("");
    if (step === 3) {
      setStep(2);
      setFormOpen(true);
      return;
    }
    if (step === 2) {
      setFormOpen(false);
      setStep(1);
    }
  }

  async function startTraining() {
    if (!form.stage || !form.goal) {
      onError("请选择商机阶段和训练目标。");
      return;
    }
    const message = validateCustomerForm();
    if (message) {
      onError(message);
      setStep(2);
      setFormOpen(true);
      return;
    }
    const nextForm = { ...form, owner_name: ownerName || form.owner_name };
    try {
      setIsSubmitting(true);
      await onStarted(buildTrainingPayload(nextForm), form.training_type, nextForm);
    } catch (err) {
      setIsSubmitting(false);
      onError(err.message);
    }
  }

  return (
    <section className="page start-wizard">
      <div className="wizard-steps" aria-label="训练步骤">
        {[
          [1, "模式"],
          [2, formOpen ? "信息" : "模板"],
          [3, "目标"],
        ].map(([id, label]) => (
          <span key={id} className={`wizard-step ${step === id ? "active" : ""} ${step > id ? "done" : ""}`}>
            <i>{id}</i>
            <em>{label}</em>
          </span>
        ))}
      </div>

      {step === 1 && (
        <div className="wizard-panel">
          <h3>这次怎么练？</h3>
          <div className="mode-cards mode-cards-full" role="radiogroup" aria-label="训练模式">
            {[
              ["客户情景陪练", "对话练话术", "和 AI 客户多轮对话，结束后出复盘报告"],
              ["商机推进教练", "出推进方案", "不进对话，直接生成判断 / 策略 / 动作"],
            ].map(([mode, short, desc]) => (
              <button
                type="button"
                key={mode}
                role="radio"
                aria-checked={form.training_type === mode}
                className={`mode-card ${form.training_type === mode ? "active" : ""}`}
                onClick={() => pickMode(mode)}
              >
                <b>{short}</b>
                <span>{desc}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {step === 2 && !formOpen && (
        <div className="wizard-panel">
          <h3>选个模板</h3>
          <p className="hint">点选后可继续改；也可以不选模板自己填。</p>
          <div className="template-list wizard-templates">
            {visibleTemplates.map((template) => (
              <button
                key={template.id}
                type="button"
                className={`template-chip ${form.template_id === template.id ? "active" : ""}`}
                onClick={() => pickTemplate(template)}
              >
                <span className="template-chip-top">
                  <b>{template.title}</b>
                  <em>{template.customer_type}</em>
                </span>
                <span className="template-chip-sub">{template.subtitle}</span>
                <small>{template.stage} · {template.goal}</small>
              </button>
            ))}
            {!visibleTemplates.length && <p className="hint">该模式下暂无模板。</p>}
          </div>
          <div className="wizard-foot wizard-foot-end">
            <button type="button" className="secondary" onClick={goBack}>返回</button>
            <button type="button" className="primary" onClick={pickFreeForm}>不选模板，自由填写</button>
          </div>
        </div>
      )}

      {step === 2 && formOpen && (
        <div className="wizard-panel">
          <h3>{form.template_id ? "确认训练信息" : "填写训练信息"}</h3>
          {form.template_id ? <p className="hint">已套用模板，可直接修改。</p> : <p className="hint">填完点下一步。</p>}

          {form.plan_training && (
            <div className="plan-focus-bar">
              <div className="section-title">
                <h4>来自推进方案</h4>
                <span className="tag">训练焦点</span>
              </div>
              {form.plan_training.plan_summary ? <p className="hint">{form.plan_training.plan_summary}</p> : null}
            </div>
          )}

          <div className="form customer-info-form">
            <label>客户名称<input value={form.customer_name} onChange={(e) => updateForm({ customer_name: e.target.value })} /></label>
            <label>产品<input value={form.product_name} onChange={(e) => updateForm({ product_name: e.target.value })} /></label>
            <label>
              客户关系
              <select
                value={form.customer_type}
                onChange={(e) => {
                  setRelationshipTouched(true);
                  updateForm({ customer_type: e.target.value });
                }}
              >
                {customerRelationshipOptions.map((item) => <option key={item}>{item}</option>)}
              </select>
            </label>
            <label>客户画像<select value={form.customer_persona || ""} onChange={(e) => updateForm({ customer_persona: e.target.value })}>{customerPersonaOptions.map((item) => <option key={item}>{item}</option>)}</select></label>
            <label className="demand-field">需求<textarea rows={3} value={form.product_need} onChange={(e) => updateForm({ product_need: e.target.value })} placeholder="客户想解决什么问题、有什么硬条件" /></label>
            <label className="demand-field">背景<textarea rows={3} value={form.background} onChange={(e) => updateForm({ background: e.target.value })} placeholder="客户是谁、卡在哪里、希望推进到哪一步" /></label>
          </div>

          <button type="button" className="text-button extra-toggle" onClick={() => setShowExtraFields((v) => !v)} aria-expanded={showExtraFields}>
            {showExtraFields ? "收起客户设定" : "展开客户设定（难度 / 性格 / 关注点）"}
          </button>
          {showExtraFields && (
            <div className="profile-tuning extra-fields">
              <label>客户难度<select value={form.customer_difficulty} onChange={(e) => updateForm({ customer_difficulty: e.target.value })}>{customerDifficultyOptions.map((item) => <option key={item}>{item}</option>)}</select></label>
              <label>客户性格<select value={form.customer_personality} onChange={(e) => updateForm({ customer_personality: e.target.value })}>{customerPersonalityOptions.map((item) => <option key={item}>{item}</option>)}</select></label>
              <label>核心关注<select value={form.customer_concern} onChange={(e) => updateForm({ customer_concern: e.target.value })}>{customerConcernOptions.map((item) => <option key={item}>{item}</option>)}</select></label>
            </div>
          )}

          {isOpportunity && (
            <div className="coach-panel visible">
              <div className="coach-panel-inner">
                <div className="section-title"><h4>商机推进诊断</h4></div>
                <div className="form coach-form">
                  <label>最近一次沟通结果<textarea rows={3} value={form.last_contact} onChange={(e) => updateForm({ last_contact: e.target.value })} placeholder="约了谁、谈到哪一步、还差什么" /></label>
                  <label>关键阻碍<select value={form.decision_blocker} onChange={(e) => updateForm({ decision_blocker: e.target.value })}>{["关键人未参与", "价格未达预期", "样品或测试未完成", "账期或付款压力", "竞品正在替代"].map((item) => <option key={item}>{item}</option>)}</select></label>
                  <label>下一步里程碑<select value={form.next_milestone} onChange={(e) => updateForm({ next_milestone: e.target.value })}>{["约到关键人会议", "取得样品或测试条件", "确认报价反馈", "确认合同或订单节点", "确认回款时间"].map((item) => <option key={item}>{item}</option>)}</select></label>
                  <label>关键人参与情况<textarea rows={3} value={form.stakeholder} onChange={(e) => updateForm({ stakeholder: e.target.value })} placeholder="采购 / 技术 / 老板分别谁参与、卡在哪" /></label>
                </div>
              </div>
            </div>
          )}

          <div className="wizard-foot">
            <button type="button" className="secondary" onClick={goBack}>返回</button>
            <button type="button" className="primary" onClick={goStageStep}>下一步</button>
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="wizard-panel">
          <h3>选阶段和目标</h3>

          <div className="quick-start">
            <div className="section-title stage-section-title">
              <h4>商机阶段</h4>
              <span className="hint">{activeStage.note}</span>
            </div>
            <div className="stage-scroll">
              <div className="stage-scroll-track" ref={stageTabsRef}>
                {opportunityStages.map((stage) => (
                  <button
                    key={stage.name}
                    type="button"
                    className={`stage-pill ${form.stage === stage.name ? "active" : ""}`}
                    onClick={() => selectStage(stage)}
                  >
                    {stage.name}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="stage-goals">
            <div className="section-title">
              <h4>训练目标 · 选一个</h4>
            </div>
            <div className="goal-grid secondary-goals">
              {activeGoals.map((goal) => (
                <button
                  key={goal.id}
                  type="button"
                  className={`goal ${form.goal === goal.name ? "active" : ""}`}
                  onClick={() => selectGoal(goal.name)}
                >
                  <span className="goal-head">
                    <span className="goal-mark" aria-hidden="true">{goalIcon(goal.id)}</span>
                    <b>{goal.name}</b>
                    {goal.recommended ? <em className="goal-rec">推荐</em> : null}
                  </span>
                  <span className="goal-desc">{goal.desc}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="wizard-foot">
            <button type="button" className="secondary" onClick={goBack}>返回</button>
            {isSubmitting ? (
              <span className="submit-waiting" role="status" aria-live="polite">
                <i /><span>{isOpportunity ? "正在生成推进方案…" : "正在创建训练…"}</span>
              </span>
            ) : (
              <button type="button" className="primary" onClick={startTraining}>
                {isOpportunity ? "生成推进方案" : "开始训练"}
              </button>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
