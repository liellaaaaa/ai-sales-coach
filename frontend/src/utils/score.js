export const SCORE_DIMENSION_ORDER = ["SOP执行", "客户洞察", "需求澄清", "异议处理", "价值表达", "推进动作", "话术质量"];

export function scoreToneClass(value) {
  const score = Number(value) || 0;
  if (score <= 1) return "score-one";
  if (score === 2) return "score-two";
  if (score === 3) return "score-three";
  if (score === 4) return "score-four";
  return "score-five";
}

export function trendScoreColor(value) {
  const score = Number(value) || 0;
  if (score < 40) return "#ea4335";
  if (score < 60) return "#f97316";
  if (score < 75) return "#fbbc04";
  if (score < 85) return "#34a853";
  return "#188038";
}

export function buildScoreTrend(values) {
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

export function scoreLevelLabel(value) {
  const score = Number(value) || 0;
  if (score <= 1) return "严重短板";
  if (score === 2) return "需补强";
  if (score === 3) return "可巩固";
  if (score === 4) return "表现稳定";
  return "优势项";
}

export function normalizeDashboardScores(items) {
  const source = Array.isArray(items) ? items : [];
  const byName = new Map(source.map((item) => [item.name, { ...item, value: Number(item.value) || 0 }]));
  return SCORE_DIMENSION_ORDER.map((name) => byName.get(name) || { name, value: 0, count: 0 });
}

export function cleanDashboardLabel(value) {
  const text = String(value || "").trim();
  if (!text || /^\?+$/.test(text)) return "";
  if (/urgent|competitor|discount|objection/i.test(text)) return "价格异议";
  if (text.length > 18) return `${text.slice(0, 18)}...`;
  return text;
}

export function distributionRows(distribution, limit = 5) {
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

export function cleanTaskText(text) {
  const cleaned = String(text || "")
    .replace(/^下一轮训练[:：]\s*/, "")
    .replace(/^下一轮(?:先)?(?:增加|补充|重点)?(?:演练|练习|训练)[:：]?\s*/, "")
    .replace(/^训练[:：]\s*/, "")
    .trim();
  return cleaned;
}

export function compactTaskLabel(text) {
  const cleaned = cleanTaskText(text);
  const quoted = cleaned.match(/[""'']([^""'']{2,10})[""'']/);
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

export function buildTrainingTask(text, index) {
  const detail = cleanTaskText(text);
  const title = compactTaskLabel(text);
  const purpose = trainingTaskPurpose(detail, title);
  const due = trainingTaskDue(detail, index);
  return { title, purpose, due, detail };
}

export function trainingTaskPurpose(detail, title) {
  if (/价值表达|色牢度|返修|稳定性|总成本|成本/.test(detail + title)) return "把产品价值说清楚，避免只停留在价格比较。";
  if (/邮件|只接收邮件|发邮件/.test(detail + title)) return "客户不愿见面时，也能把下一步动作推进下去。";
  if (/关键人/.test(detail + title)) return "找到真实决策链，减少单点沟通造成的停滞。";
  if (/价格|报价|降价|压价/.test(detail + title)) return "先确认异议来源，再判断是否需要谈条件。";
  if (/时间|条件|节点|承诺/.test(detail + title)) return "把模糊沟通收敛成明确的人、时间和条件。";
  if (/需求|工艺|测试/.test(detail + title)) return "补齐客户判断标准，让方案论证更有依据。";
  if (/异议|拒绝|反对|担心/.test(detail + title)) return "承接客户顾虑，并转成可继续推进的问题。";
  return "把本轮短板转成下一次可练习、可复盘的开口动作。";
}

export function trainingTaskDue(detail, index) {
  if (/时间|节点|关键人|推进|邮件/.test(detail)) return "1 天内";
  if (/价格|报价|异议|价值|成本/.test(detail)) return "2 天内";
  if (/工艺|测试|色牢度|方案/.test(detail)) return "3 天内";
  return `${Math.min(index + 1, 3)} 天内`;
}

export function formatDate(value) {
  return new Date(value).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}
