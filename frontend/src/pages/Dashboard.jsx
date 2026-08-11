import React from "react";
import { normalizeDashboardScores, distributionRows, buildScoreTrend, trendScoreColor } from "../utils/score";
import AbilityRadar from "../components/AbilityRadar";
import { Empty } from "../components/Layout";

function DistributionRow({ item }) {
  return (
    <div className="distribution-row">
      <span>{item.name}</span>
      <i style={{ "--value": `${item.percent}%` }}><b /></i>
      <em>{item.value}</em>
    </div>
  );
}

export default function Dashboard({ summary }) {
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
            <p>{weakDimension ? `围绕"${weakDimension.name}"做 1 次客户情景陪练，并在复盘里确认话术是否更具体。` : "先完成一次客户情景陪练，生成第一份能力画像。"}</p>
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
