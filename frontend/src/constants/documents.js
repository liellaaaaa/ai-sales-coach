import { opportunityStages, stageTrainingGoals } from "./training";

export const documentUploadDefaults = {
  source_type: "SOP 与话术",
  tags: "",
};

export const documentTypeOptions = ["SOP 与话术", "产品说明书"];
export const documentTagPresets = {
  "SOP 与话术": ["销售流程", "商务谈判", "价格异议", "异议处理", "推荐话术", "禁用话术", "评分标准", "回款交涉"],
  "产品说明书": ["产品参数", "工艺条件", "应用场景", "使用方法", "注意事项", "技术边界", "价值表达", "常见问题"],
};
export const documentTagKeywords = {
  销售流程: ["销售流程", "流程", "阶段", "商机", "跟进"],
  商务谈判: ["商务谈判", "谈判", "报价", "账期", "交付"],
  价格异议: ["价格", "降价", "报价", "贵", "成本"],
  异议处理: ["异议", "反对", "顾虑", "拒绝", "疑虑"],
  推荐话术: ["推荐话术", "建议话术", "标准话术", "话术"],
  禁用话术: ["禁用", "不要说", "避免", "禁止"],
  评分标准: ["评分", "标准", "考核", "评价"],
  回款交涉: ["回款", "付款", "账期", "催款"],
  产品参数: ["参数", "指标", "含量", "规格", "ph", "粘度"],
  工艺条件: ["工艺", "温度", "时间", "浴比", "条件"],
  应用场景: ["应用", "适用", "场景", "用于", "客户"],
  使用方法: ["使用方法", "用法", "添加", "操作", "步骤"],
  注意事项: ["注意", "事项", "储存", "安全", "避免"],
  技术边界: ["边界", "限制", "不适用", "风险", "兼容"],
  价值表达: ["价值", "优势", "稳定", "成本", "效率"],
  常见问题: ["faq", "常见问题", "问题", "解答"],
};
export const documentPageSizes = [20, 50, 100];
export const chunkStageOptions = ["", "通用", ...opportunityStages.map((item) => item.name)];
export const chunkScenarioOptions = [
  "",
  "通用",
  ...new Set(Object.values(stageTrainingGoals).flat().map((item) => item.name)),
];
