import React from "react";
import {
  normalizeDashboardScores,
  distributionRows,
  buildScoreTrend,
  trendScoreColor,
} from "../utils/score";
import AbilityRadar from "../components/AbilityRadar";
import { Empty } from "../components/Layout";

function PieChart({ items, title }) {
  const rows = (items || []).filter((item) => item.value > 0).slice(0, 6);
  const total = rows.reduce((sum, item) => sum + (Number(item.value) || 0), 0);
  const colors = ["#1a73e8", "#34a853", "#fbbc04", "#ea4335", "#7c4dff", "#00b8a9"];
  const size = 120;
  const radius = 48;
  const cx = size / 2;
  const cy = size / 2;
  let angle = -Math.PI / 2;
  const slices = rows.map((item, index) => {
    const ratio = total ? item.value / total : 0;
    const start = angle;
    const end = angle + ratio * Math.PI * 2;
    angle = end;
    const x1 = cx + radius * Math.cos(start);
    const y1 = cy + radius * Math.sin(start);
    const x2 = cx + radius * Math.cos(end);
    const y2 = cy + radius * Math.sin(end);
    const large = ratio > 0.5 ? 1 : 0;
    return {
      ...item,
      color: colors[index % colors.length],
      percent: Math.round(ratio * 100),
      path: rows.length === 1
        ? `M ${cx - radius} ${cy} A ${radius} ${radius} 0 1 1 ${cx + radius} ${cy} A ${radius} ${radius} 0 1 1 ${cx - radius} ${cy} Z`
        : `M ${cx} ${cy} L ${x1} ${y1} A ${radius} ${radius} 0 ${large} 1 ${x2} ${y2} Z`,
    };
  });

  return (
    <div className="pie-block">
      <b className="pie-title">{title}</b>
      {!rows.length ? (
        <p className="small">暂无分布数据。</p>
      ) : (
        <div className="pie-layout">
          <svg className="pie-svg" viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`${title}分布`}>
            {slices.map((slice) => (
              <path key={slice.name} d={slice.path} fill={slice.color} />
            ))}
            <circle cx={cx} cy={cy} r="28" fill="#fff" />
            <text x={cx} y={cy - 2} textAnchor="middle" dominantBaseline="central" className="pie-center-num">{total}</text>
            <text x={cx} y={cy + 12} textAnchor="middle" dominantBaseline="central" className="pie-center-label">次</text>
          </svg>
          <ul className="pie-legend">
            {slices.map((slice) => (
              <li key={slice.name}>
                <i style={{ background: slice.color }} />
                <span>{slice.name}</span>
                <em>{slice.percent}%</em>
              </li>
            ))}
          </ul>
        </div>
      )}
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
  const hasScoreData = completedCount > 0 || scoreAverages.some((item) => item.value > 0);
  const weakDimensions = [...scoreAverages].filter((item) => item.value > 0).sort((a, b) => a.value - b.value).slice(0, 3);
  const weakDimension = weakDimensions[0];
  const topGoal = goals[0];
  const recentScores = Array.isArray(summary.recent_scores) ? summary.recent_scores.slice(-10) : [];
  const scoreTrend = buildScoreTrend(recentScores.map((item) => item.score));
  const latestScore = recentScores[recentScores.length - 1]?.score || averageScore;
  const previousScore = recentScores[recentScores.length - 2]?.score || latestScore;
  const scoreDelta = Math.round((latestScore - previousScore) * 10) / 10;
  const nextFocus = weakDimension?.name || topGoal?.name || "价格异议";
  return (
    <section className="page dashboard-page">
      <div className="profile-metrics">
        <article><span>训练次数</span><strong>{trainingCount}</strong><p>累计训练记录</p></article>
        <article><span>复盘完成</span><strong>{completedCount}</strong><p>{completeRate}% 已形成报告</p></article>
        <article><span>最近均分</span><strong>{averageScore || "-"}</strong><p>{scoreDelta > 0 ? `较上次 +${scoreDelta}` : scoreDelta < 0 ? `较上次 ${scoreDelta}` : "保持稳定"}</p></article>
        <article><span>待完成</span><strong>{activeCount}</strong><p>可继续对话或复盘</p></article>
      </div>

      {!hasScoreData ? (
        <section className="profile-panel dashboard-empty-cta">
          <div className="profile-section-head">
            <div><span>能力画像</span><h4>完成一次复盘后生成</h4></div>
            <p>七项能力均分、优势和补强会出现在这里。</p>
          </div>
          <div className="action-card primary-action">
            <span>下一步</span>
            <strong>先跑完一次客户情景陪练</strong>
            <p>练完并生成报告后，这里会给出能力雷达和本周训练建议。</p>
          </div>
        </section>
      ) : (
        <>
          <div className="profile-grid">
            <section className="profile-panel ability-overview">
              <div className="profile-section-head">
                <div><span>能力画像</span><h4>七项能力均分</h4></div>
                <p>来自已完成复盘报告的分项评分。</p>
              </div>
              <div className="profile-ability-layout">
                <AbilityRadar scores={scoreAverages} />
              </div>
            </section>
            <section className="profile-panel action-center">
              <div className="profile-section-head">
                <div><span>下一步行动</span><h4>本周训练建议</h4></div>
              </div>
              <div className="action-card primary-action">
                <span>优先练习</span>
                <strong>{nextFocus}</strong>
                <p>{weakDimension ? `围绕"${weakDimension.name}"做 1 次客户情景陪练，复盘里确认话术是否更具体。` : "先完成一次客户情景陪练，生成第一份能力画像。"}</p>
              </div>
              <div className="action-steps">
                <span>建议节奏</span>
                <p>3 天内完成 1 次对话训练，再用同一背景生成 1 份商机推进方案。</p>
              </div>
            </section>
          </div>
          <div className="profile-grid lower">
            <section className="profile-panel trend-panel">
              <div className="profile-section-head">
                <div><span>成长趋势</span><h4>最近 10 次得分</h4></div>
                {scoreTrend.points.length > 0 && (
                  <p>共 {scoreTrend.points.length} 次 · 均分 {averageScore || "-"}</p>
                )}
              </div>
              <div className="score-trend-line">
                {scoreTrend.points.length ? (
                  <svg viewBox={`0 0 ${scoreTrend.width} ${scoreTrend.height}`} role="img" aria-label="最近 10 次训练得分折线趋势">
                    <defs>
                      <linearGradient id="scoreTrendArea" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#1a73e8" stopOpacity="0.22" />
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
              <div className="profile-section-head">
                <div><span>训练结构</span><h4>高频场景与阶段</h4></div>
                <p>看最近训练是否过度集中。</p>
              </div>
              <div className="distribution-columns pie-columns">
                <PieChart items={goals} title="目标分布" />
                <PieChart items={stages} title="阶段覆盖" />
              </div>
            </section>
          </div>
        </>
      )}
    </section>
  );
}
