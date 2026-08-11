import { documentUploadDefaults, documentTagPresets, documentTagKeywords } from "../constants/documents";

export function splitDocumentTags(value) {
  return (value || "")
    .split(/[、,，\s]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function toggleDocumentTag(value, tag) {
  const tags = splitDocumentTags(value);
  const nextTags = tags.includes(tag) ? tags.filter((item) => item !== tag) : [...tags, tag];
  return nextTags.join("、");
}

export function fileExtensionLabel(file) {
  const ext = file?.name?.split(".").pop();
  return ext ? ext.toUpperCase() : "FILE";
}

export function fileSizeLabel(size = 0) {
  if (!size) return "0 KB";
  if (size < 1024 * 1024) return `${Math.max(1, Math.round(size / 1024))} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

export function analysisStatusText(status) {
  return {
    analyzing: "正在分析内容",
    ready: "已完成预分析",
    error: "已使用本地规则预选",
    idle: "等待选择文件",
  }[status] || "等待选择文件";
}

export function analysisStatusTitle(status) {
  return {
    analyzing: "LLM 预分析中",
    ready: "预分析完成",
    error: "预分析兜底",
    idle: "等待文件",
  }[status] || "等待文件";
}

export async function readDocumentPreview(file) {
  if (!file) return "";
  const lowerName = file.name.toLowerCase();
  const isTextLike = file.type.startsWith("text/") || lowerName.endsWith(".txt") || lowerName.endsWith(".md");
  if (!isTextLike) return "";
  try {
    return (await file.text()).slice(0, 8000);
  } catch {
    return "";
  }
}

export function inferDocumentSourceType(file, fallback, preview = "") {
  const text = `${file?.name || ""} ${preview}`.toLowerCase();
  if (/(说明书|产品|参数|工艺|使用方法|application|spec|manual)/i.test(text)) return "产品说明书";
  if (/(sop|话术|销售流程|商务谈判|评分标准|禁用话术|异议处理)/i.test(text)) return "SOP 与话术";
  return fallback || documentUploadDefaults.source_type;
}

export function inferDocumentTags(file, sourceType, preview = "") {
  const presets = documentTagPresets[sourceType] || [];
  const text = `${file?.name || ""} ${preview}`.toLowerCase();
  const matched = presets.filter((tag) => (documentTagKeywords[tag] || []).some((keyword) => text.includes(keyword.toLowerCase())));
  if (matched.length) return matched.slice(0, 5);
  return sourceType === "产品说明书" ? ["产品参数", "应用场景"] : ["销售流程", "推荐话术"];
}

export function parseStatusLabel(status) {
  return {
    parsed: "已解析",
    pending: "解析中",
    empty: "无有效正文",
    quality_low: "解析质量不足",
    failed: "解析失败",
  }[status] || status || "未知";
}
