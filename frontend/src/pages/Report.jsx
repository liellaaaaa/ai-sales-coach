import React, { useState } from "react";
import { OPPORTUNITY_MODE } from "../constants/training";
import { normalizeTextList, normalizeStrategies, normalizeTodos, buildSpeechPair } from "../utils/report";
import { scoreToneClass, scoreLevelLabel, buildTrainingTask } from "../utils/score";
import AbilityRadar from "../components/AbilityRadar";
import { Empty } from "../components/Layout";

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

export default function Report({ report }) {
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
    ? `本轮最大问题集中在"${weakScore.name}"，客户已经给出反馈，但还需要把下一步推进到明确的人、时间和条件。`
    : "本轮可以承接客户反馈，下一步需要继续把对话收敛到明确推进动作。";
  const retrainFocus = weakScore
    ? `下一轮重点围绕"${weakScore.name}"练习，把客户反馈拆成明确的人员、时间或条件。`
    : "下一轮重点练习确认关键人、时间和测试条件。";
  const speechPair = buildSpeechPair(report, review);
  const opportunityStrategies = normalizeStrategies(report.alternatives);
  const opportunityTodos = normalizeTodos(report.checklist, report.alternatives);
  const opportunityActions = opportunityTodos.map((item) => item.detail).filter(Boolean);
  const primaryOpportunityAction = opportunityTodos[0]?.detail || opportunityStrategies[0]?.text || "把下一步推进动作收敛到一个明确的人员、时间和条件。";
  const opportunityQuestion = opportunityContext?.decision_blocker
    ? `针对"${opportunityContext.decision_blocker}"，直接确认：这件事由谁判断、什么时候能给反馈、需要我们补什么材料？`
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
