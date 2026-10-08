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
  apiGoalFromDisplay,
  trainingTemplates,
  defaultForm,
} from "../constants/training";
import { buildTrainingPayload } from "../utils/training";
import { goalIcon } from "../components/Layout";

function SectionHead({ index, title, desc, right }) {
  return (
    <div className="flow-section-head">
      <div className="flow-section-title">
        <span className="flow-index" aria-hidden="true">{index}</span>
        <div>
          <h4>{title}</h4>
          {desc ? <p className="hint">{desc}</p> : null}
        </div>
      </div>
      {right ? <div className="flow-section-right">{right}</div> : null}
    </div>
  );
}

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

export default function StartTraining({ onStarted, onError, recordCount, user, planDraft, onPlanDraftApplied }) {
  const ownerName = user?.name || user?.username || "";
  const [form, setForm] = useState(() => mergePlanDraft({ ...defaultForm, owner_name: ownerName }, planDraft, ownerName));
  const [showExtraFields, setShowExtraFields] = useState(false);
  const [showFlowRef, setShowFlowRef] = useState(false);
  const [relationshipTouched, setRelationshipTouched] = useState(Boolean(planDraft));
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const stageTabsRef = useRef(null);

  // 推进方案带入：合并进表单后立刻消费掉，避免下次进页重复套用
  useEffect(() => {
    if (!planDraft) return;
    setForm((prev) => mergePlanDraft(prev, planDraft, ownerName));
    setRelationshipTouched(true);
    onPlanDraftApplied?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [planDraft]);

  const planTraining = form.plan_training;

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

  function validateSetup() {
    if (!form.customer_name.trim() || !form.product_name.trim() || !form.customer_type.trim() || !form.product_need.trim()) {
      return "请先补齐客户名称、产品、客户关系和需求。";
    }
    if (isOpportunity && (!form.last_contact.trim() || !form.stakeholder.trim())) {
      return "商机推进教练需要补充最近一次沟通结果和关键人参与情况。";
    }
    if (!form.stage || !form.goal) {
      return "请选择商机阶段和训练目标。";
    }
    return "";
  }

  function applyTemplate(template) {
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
    onError("");
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

  function openConfirm(event) {
    event.preventDefault();
    const message = validateSetup();
    if (message) {
      onError(message);
      return;
    }
    onError("");
    setShowConfirm(true);
  }

  async function confirmStart() {
    const nextForm = { ...form, owner_name: ownerName || form.owner_name };
    try {
      setIsSubmitting(true);
      await onStarted(buildTrainingPayload(nextForm), form.training_type, nextForm);
      setShowConfirm(false);
    } catch (err) {
      setIsSubmitting(false);
      onError(err.message);
    }
  }

  return (
    <section className="page knowledge-page start-training-page">
      <div className="hero start-hero">
        <div className="intro">
          <span className="eyebrow">训练闭环</span>
          <h3>一页配好，开练前再确认一次</h3>
          <p className="hint">模式和客户信息填好，选阶段与目标后点开始；弹窗核对无误再进入训练。</p>
        </div>
        <div className="metric-card compact-metric">
          <span className="small">本地训练记录</span>
          <strong>{recordCount}</strong>
          <p className="small">完成训练后自动保存</p>
        </div>
      </div>

      {planTraining && (
        <div className="plan-focus-bar">
          <div className="section-title">
            <h4>来自推进方案</h4>
            <span className="tag">训练焦点</span>
          </div>
          {planTraining.plan_summary ? <p className="hint">{planTraining.plan_summary}</p> : null}
          <div className="plan-focus-grid">
            <div>
              <span>优先推进动作</span>
              <p>{planTraining.primary_action || "—"}</p>
            </div>
            <div>
              <span>必须问清</span>
              <p>{planTraining.must_ask || "—"}</p>
            </div>
          </div>
          {!!planTraining.checklist?.length && (
            <details className="plan-focus-details">
              <summary>执行清单（{planTraining.checklist.length}）</summary>
              <ol>
                {planTraining.checklist.map((item, index) => (
                  <li key={index}>
                    <b>{item.title}</b>
                    <p>{item.detail}</p>
                    {item.due ? <em>{item.due}</em> : null}
                  </li>
                ))}
              </ol>
            </details>
          )}
        </div>
      )}

      <form className="setup-canvas" onSubmit={openConfirm}>
        <section className="flow-section">
          <SectionHead
            index="1"
            title="练什么模式"
            desc="情景陪练进对话；推进教练出方案。"
            right={<span className="training-step-pill"><span>第 1 段</span><b>模式与模板</b></span>}
          />
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
                onClick={() => updateForm({ training_type: mode })}
              >
                <b>{short}</b>
                <span>{desc}</span>
              </button>
            ))}
          </div>

          <div className="template-block">
            <div className="section-title"><h4>常用训练模板</h4><span className="hint">点选后可继续改</span></div>
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
                    <em>{template.customer_type}</em>
                  </span>
                  <span className="template-chip-sub">{template.subtitle}</span>
                  <small>{template.stage} · {template.goal}</small>
                </button>
              ))}
              {!visibleTemplates.length && <p className="hint">该模式下暂无模板，可直接填写客户信息。</p>}
            </div>
          </div>
        </section>

        <section className="flow-section">
          <SectionHead
            index="2"
            title="跟谁练"
            desc="客户关系只表示有没有合作；性格和关注点独立选择。"
            right={<span className="training-step-pill"><span>第 2 段</span><b>客户信息</b></span>}
          />
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

          <div className={`coach-panel ${isOpportunity ? "visible" : ""}`}>
            <div className="coach-panel-inner">
              <div className="section-title"><h4>商机推进诊断</h4><span className="tag">推进教练专用</span></div>
              <div className="form coach-form">
                <label>最近一次沟通结果<textarea rows={3} value={form.last_contact} onChange={(e) => updateForm({ last_contact: e.target.value })} placeholder="约了谁、谈到哪一步、还差什么" /></label>
                <label>关键阻碍<select value={form.decision_blocker} onChange={(e) => updateForm({ decision_blocker: e.target.value })}>{["关键人未参与", "价格未达预期", "样品或测试未完成", "账期或付款压力", "竞品正在替代"].map((item) => <option key={item}>{item}</option>)}</select></label>
                <label>下一步里程碑<select value={form.next_milestone} onChange={(e) => updateForm({ next_milestone: e.target.value })}>{["约到关键人会议", "取得样品或测试条件", "确认报价反馈", "确认合同或订单节点", "确认回款时间"].map((item) => <option key={item}>{item}</option>)}</select></label>
                <label>关键人参与情况<textarea rows={3} value={form.stakeholder} onChange={(e) => updateForm({ stakeholder: e.target.value })} placeholder="采购 / 技术 / 老板分别谁参与、卡在哪" /></label>
              </div>
            </div>
          </div>
        </section>

        <section className="flow-section">
          <SectionHead
            index="3"
            title="这次练什么"
            desc="阶段决定位置，目标决定这一练的重点。目标只显示当前阶段相关项。"
            right={<span className="training-step-pill is-active"><span>第 3 段</span><b>阶段与目标</b></span>}
          />

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
              <span className="stage-scroll-fade" aria-hidden="true"><i>›</i></span>
            </div>

            <button type="button" className="text-button stage-toggle-label" onClick={() => setShowFlowRef((v) => !v)} aria-expanded={showFlowRef}>
              {showFlowRef ? "收起参考动作" : `参考动作（${activeStage.flow.length}）· 不是选项`}
            </button>
            {showFlowRef && (
              <div className="flow-list compact-flow">
                {activeStage.flow.map(([name, summary], index) => (
                  <div className="flow-item" key={name}><span className="flow-index">{index + 1}</span><span><b>{name}</b><small>{summary}</small></span></div>
                ))}
              </div>
            )}
          </div>

          <div className="stage-goals">
            <div className="section-title">
              <h4>训练目标 · 选一个</h4>
              <span className="hint">随「{form.stage}」联动，推荐项已标出</span>
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

          <label className="field full">一句话描述当前客户 / 商机问题
            <textarea
              rows={4}
              value={form.background}
              onChange={(e) => updateForm({ background: e.target.value })}
              placeholder="客户是谁、卡在哪里、你希望推进到哪一步"
            />
          </label>
        </section>

        <div className="actions train-submit-actions start-rail">
          <div className="start-rail-summary" aria-live="polite">
            <span>{form.training_type}</span>
            <b>{form.stage}</b>
            <b>{form.goal}</b>
            <span>{form.customer_name || "未填客户"}</span>
          </div>
          {isSubmitting ? (
            <span className="submit-waiting" role="status" aria-live="polite">
              <i /><span>{isOpportunity ? "正在生成推进方案，请稍等。" : "正在创建训练对话，请稍等。"}</span>
            </span>
          ) : (
            <button className="primary" type="submit">
              {isOpportunity ? "生成推进方案" : "开始本次训练"}
            </button>
          )}
        </div>
      </form>

      {showConfirm && (
        <div className="confirm-overlay" role="dialog" aria-modal="true" aria-label="确认训练配置">
          <div className="confirm-sheet">
            <div className="confirm-head">
              <h3>确认本次训练配置</h3>
              <p className="hint">下面是将要创建的训练；有问题可返回修改。</p>
            </div>
            <div className="confirm-body">
              <div className="confirm-grid">
                <div><span>模式</span><b>{form.training_type}</b></div>
                <div><span>客户</span><b>{form.customer_name}</b></div>
                <div><span>产品</span><b>{form.product_name}</b></div>
                <div><span>客户关系</span><b>{form.customer_type}</b></div>
                <div><span>商机阶段</span><b>{form.stage}</b></div>
                <div><span>训练目标</span><b>{form.goal}</b></div>
                <div><span>客户设定</span><b>{form.customer_difficulty} · {form.customer_personality} · {form.customer_concern}</b></div>
                {isOpportunity ? <div><span>关键阻碍</span><b>{form.decision_blocker}</b></div> : null}
                {isOpportunity ? <div><span>下一步</span><b>{form.next_milestone}</b></div> : null}
              </div>
              <div className="confirm-background">
                <span>背景摘要</span>
                <p>{form.background}</p>
              </div>
              {form.plan_training && (
                <div className="confirm-plan-focus">
                  <span>训练焦点</span>
                  <p>{form.plan_training.plan_summary}</p>
                  <p>优先推进动作：{form.plan_training.primary_action}</p>
                  <p>必须问清：{form.plan_training.must_ask}</p>
                </div>
              )}
            </div>
            <div className="confirm-actions">
              <button type="button" className="secondary" onClick={() => setShowConfirm(false)} disabled={isSubmitting}>返回修改</button>
              <button type="button" className="primary" onClick={confirmStart} disabled={isSubmitting}>
                {isSubmitting ? (isOpportunity ? "生成中…" : "创建中…") : (isOpportunity ? "确认生成方案" : "确认开始训练")}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
