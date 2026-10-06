import React, { useRef, useState } from "react";
import {
  TRAINING_TYPES,
  OPPORTUNITY_MODE,
  opportunityStages,
  stageTrainingGoals,
  trainingGoals,
  customerDifficultyOptions,
  customerPersonalityOptions,
  customerConcernOptions,
  trainingTemplates,
  defaultForm,
} from "../constants/training";
import { buildTrainingPayload } from "../utils/training";
import { goalIcon } from "../components/Layout";

export default function StartTraining({ onStarted, onError, recordCount, user }) {
  const ownerName = user?.name || user?.username || "";
  const [form, setForm] = useState(() => ({ ...defaultForm, owner_name: ownerName }));
  const [stageExpanded, setStageExpanded] = useState(false);
  const [setupSaved, setSetupSaved] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showExtraFields, setShowExtraFields] = useState(false);
  const stageTabsRef = useRef(null);
  const isOpportunity = form.training_type === OPPORTUNITY_MODE;
  const stageIndex = Math.max(0, opportunityStages.findIndex((item) => item.name === form.stage));
  const activeStage = opportunityStages[stageIndex];
  const activeGoals = stageTrainingGoals[activeStage.name] || trainingGoals;
  const visibleTemplates = trainingTemplates.filter((item) => item.training_type === form.training_type);
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
    const nextForm = { ...form, owner_name: ownerName || form.owner_name };
    try {
      setIsSubmitting(true);
      await onStarted(buildTrainingPayload(nextForm), form.training_type, nextForm);
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
    const nextOwner = ownerName || form.owner_name;
    if (!form.customer_name.trim() || !form.product_name.trim() || !form.customer_type.trim() || !form.product_need.trim()) {
      onError("请先补齐客户名称、产品、客户类型和需求。");
      return;
    }
    if (isOpportunity && (!form.last_contact.trim() || !form.stakeholder.trim())) {
      onError("商机推进教练需要补充最近一次沟通结果和关键人参与情况。");
      return;
    }
    onError("");
    setForm((prev) => ({ ...prev, owner_name: nextOwner }));
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
    <section className="page knowledge-page start-training-page">
      <div className="hero start-hero">
        <div className="intro">
          <span className="eyebrow">训练闭环</span>
          <h3>先用一句话发起训练</h3>
          <p className="hint">选模式 → 点模板或填客户信息 → 保存后选目标开练。</p>
        </div>
        <div className="metric-card compact-metric">
          <span className="small">本地训练记录</span>
          <strong>{recordCount}</strong>
          <p className="small">完成训练后自动保存</p>
        </div>
      </div>
      <form className="panel" onSubmit={submit}>
        <div className="panel-inner">
          <div className={`panel-head ${setupSaved ? "panel-head-saved" : ""}`}>
            {!setupSaved ? (
              <div className={`mode-switch-block ${isOpportunity ? "opportunity" : ""}`}>
                <div className="mode-cards" role="radiogroup" aria-label="训练模式">
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
                      onClick={() => updateSetup({ training_type: mode })}
                    >
                      <b>{short}</b>
                      <span>{desc}</span>
                    </button>
                  ))}
                </div>
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
              <div className="section-title">
                <h4>常用训练模板</h4>
                <span className="hint">当前模式 · 点选后自动带出客户信息，可再改。</span>
              </div>
              <div className="template-list">
                {visibleTemplates.map((template) => (
                  <button
                    key={template.id}
                    type="button"
                    className={`template-chip ${form.template_id === template.id ? "active" : ""}`}
                    onClick={() => applyTemplate(template)}
                  >
                    <span className="template-chip-top">
                      <b>{template.title}</b>
                      <em>{template.customer_concern}</em>
                    </span>
                    <span className="template-chip-sub">{template.subtitle}</span>
                    <small>{template.stage} · {template.customer_personality}</small>
                  </button>
                ))}
                {!visibleTemplates.length && <p className="hint">该模式下暂无模板，可直接填写客户信息。</p>}
              </div>
            </div>

            <div className="basic-fields">
              <div className="section-title"><h4>客户信息</h4><span className="hint">必填 5 项，其余可折叠。</span></div>
              <div className="form customer-info-form">
                <label>客户名称<input value={form.customer_name} onChange={(e) => updateSetup({ customer_name: e.target.value })} /></label>
                <label>产品<input value={form.product_name} onChange={(e) => updateSetup({ product_name: e.target.value })} /></label>
                <label>客户类型<select value={form.customer_type} onChange={(e) => updateSetup({ customer_type: e.target.value })}>{["老客户，订单减少", "新客户，价格敏感", "技术型客户，关注工艺", "渠道客户，关注交期"].map((item) => <option key={item}>{item}</option>)}</select></label>
                <label className="demand-field">需求<textarea rows={2} value={form.product_need} onChange={(e) => updateSetup({ product_need: e.target.value })} /></label>
              </div>
              <button type="button" className="text-button extra-toggle" onClick={() => setShowExtraFields((v) => !v)} aria-expanded={showExtraFields}>
                {showExtraFields ? "收起客户设定" : "展开客户设定（难度 / 性格 / 关注点）"}
              </button>
              {showExtraFields && (
                <div className="profile-tuning extra-fields">
                  <label>客户难度<select value={form.customer_difficulty} onChange={(e) => updateSetup({ customer_difficulty: e.target.value })}>{customerDifficultyOptions.map((item) => <option key={item}>{item}</option>)}</select></label>
                  <label>客户性格<select value={form.customer_personality} onChange={(e) => updateSetup({ customer_personality: e.target.value })}>{customerPersonalityOptions.map((item) => <option key={item}>{item}</option>)}</select></label>
                  <label>核心关注<select value={form.customer_concern} onChange={(e) => updateSetup({ customer_concern: e.target.value })}>{customerConcernOptions.map((item) => <option key={item}>{item}</option>)}</select></label>
                </div>
              )}
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
                  <h4>{form.customer_name}</h4>
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
              <div className="section-title stage-section-title">
                <h4>商机阶段</h4>
                <span className="hint">当前：<b>{activeStage.name}</b></span>
                <span className="tag">必选</span>
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
                <span className="stage-scroll-fade" aria-hidden="true"><i>›</i></span>
              </div>
              <p className="stage-note hint">{activeStage.note}</p>
              <button type="button" className="text-button stage-toggle-label" onClick={() => setStageExpanded(!stageExpanded)} aria-expanded={stageExpanded}>
                {stageExpanded ? "收起该阶段动作" : `查看动作（${activeStage.flow.length}）`}
              </button>
              {stageExpanded && (
                <div className="flow-list compact-flow">
                  {activeStage.flow.map(([name, summary], index) => (
                    <div className="flow-item" key={name}><span className="flow-index">{index + 1}</span><span><b>{name}</b><small>{summary}</small></span></div>
                  ))}
                </div>
              )}
            </div>

            <label className="field full">一句话描述当前客户 / 商机问题<textarea rows={4} value={form.background} onChange={(e) => setForm({ ...form, background: e.target.value })} placeholder="客户是谁、卡在哪里、你希望推进到哪一步" /></label>

            <div className="stage-goals">
              <div className="section-title">
                <h4>训练目标</h4>
                <span className="hint">{activeStage.name} · 选一个最贴近卡点的方向</span>
              </div>
              <div className="goal-grid secondary-goals">
                {activeGoals.map((goal) => (
                  <button key={goal.id} type="button" className={`goal ${form.goal === goal.name ? "active" : ""}`} onClick={() => setForm({ ...form, goal: goal.name })}>
                    <span className="goal-head"><span className="goal-mark" aria-hidden="true">{goalIcon(goal.id)}</span><b>{goal.name}</b></span>
                    <span className="goal-desc">{goal.desc}</span>
                  </button>
                ))}
              </div>
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
