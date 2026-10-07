export const TRAINING_TYPES = ["客户情景陪练", "商机推进教练"];
export const OPPORTUNITY_MODE = "商机推进教练";

export const opportunityStages = [
  {
    name: "了解商机",
    note: "拿到有效线索，建立直接沟通入口，并约到首次拜访。",
    flow: [
      ["线索获取", "找到潜在客户来源，判断是否值得进入跟进。"],
      ["加微信", "建立直接沟通入口，方便后续资料和拜访安排。"],
      ["约拜访", "把线上线索推进到一次明确的客户接触。"],
    ],
  },
  {
    name: "确认商机",
    note: "确认客户真实需求，尽快取得样品，并推动再次拜访。",
    flow: [
      ["首次拜访", "确认客户需求、使用场景和关键联系人。"],
      ["取得样品", "拿到样品或工艺条件，为后续方案论证做准备。"],
      ["再次拜访", "针对未完成事项继续推进客户接触。"],
    ],
  },
  {
    name: "方案论证",
    note: "围绕打样、报告、送样和试样反馈推进方案验证。",
    flow: [
      ["内部打样", "根据样品和需求组织内部方案验证。"],
      ["出具报告", "形成客户可判断的检测、对比或方案依据。"],
      ["送样试样", "把方案推进到客户试样，并跟进反馈。"],
      ["复盘重打", "试样未通过时归因并决定是否重新打样。"],
    ],
  },
  {
    name: "商务谈判",
    note: "处理报价、价格异议、账期和交付条件。",
    flow: [
      ["报价", "给出报价并解释价值、成本和交付边界。"],
      ["条件收口", "围绕价格、账期、交付和责任条件达成一致。"],
    ],
  },
  {
    name: "销售成交",
    note: "推动合同签订，并保障订单交付边界清晰。",
    flow: [
      ["签订合同", "确认合同条款、价格、交付和责任边界。"],
      ["订单交付", "推动订单按时间、质量和服务要求交付。"],
    ],
  },
  {
    name: "回款",
    note: "跟进回款事项，稳定服务体验，并推动客户复购。",
    flow: [
      ["跟进回款", "根据账期和约定节奏推进回款。"],
      ["服务复购", "稳定服务体验，并在条件成熟时推动复购。"],
    ],
  },
];

/**
 * 每阶段训练目标：展示名已合并瘦身（2–3 个）。
 * - name：界面展示 / 写入 session.goal（新词表）
 * - apiGoal：历史兼容别名（旧数据、知识库 scenario）
 * - recommended：切阶段时的默认推荐项（不要用数组下标 0）
 * - id：全局唯一，禁止复用
 */
export const stageTrainingGoals = {
  了解商机: [
    { id: "lead", name: "线索判断", apiGoal: "线索判断", desc: "判断线索是否值得跟进，并明确客户来源。", recommended: true },
    { id: "connect", name: "建立连接", apiGoal: "首次触达", desc: "加微信或打通电话，建立直接沟通入口。" },
    { id: "visit", name: "约到拜访", apiGoal: "约到拜访", desc: "把线上线索推进到一次明确的客户接触。" },
  ],
  确认商机: [
    { id: "need", name: "需求澄清", apiGoal: "需求澄清", desc: "确认真实需求、使用场景和判断标准。", recommended: true },
    { id: "sample", name: "取得样品", apiGoal: "取得样品", desc: "推动客户提供样品或工艺条件。" },
    { id: "advance", name: "再次推进", apiGoal: "再次拜访", desc: "把关键人、样品或下一步节点再推一把。" },
  ],
  方案论证: [
    { id: "solution", name: "方案讲解", apiGoal: "技术交涉", desc: "把工艺、产品方案或测试条件讲清楚。" },
    { id: "trial", name: "试样推进", apiGoal: "试样推进", desc: "推动客户完成试样并给出反馈。", recommended: true },
    { id: "objection", name: "异议应对", apiGoal: "技术质疑", desc: "客户质疑效果或出质量客诉时，先归因再谈方案。" },
  ],
  商务谈判: [
    { id: "price", name: "价格异议", apiGoal: "价格异议", desc: "客户认为报价高，需要对齐价值与让步边界。", recommended: true },
    { id: "terms", name: "条件收口", apiGoal: "条件谈判", desc: "围绕价格、账期、交付和责任条件收口。" },
  ],
  销售成交: [
    { id: "contract", name: "合同签订", apiGoal: "合同签订", desc: "推动合同条款、价格和交付边界确认。", recommended: true },
    { id: "delivery", name: "交付确认", apiGoal: "订单交付", desc: "确认交付时间、质量标准和责任边界。" },
  ],
  回款: [
    { id: "payment", name: "回款交涉", apiGoal: "回款交涉", desc: "客户拖延付款或账期压力大时推进回款。", recommended: true },
    { id: "retain", name: "关系维护", apiGoal: "老客维护", desc: "用服务体验稳住关系，降低断单风险。" },
    { id: "repurchase", name: "复购推进", apiGoal: "复购推进", desc: "在服务稳定后推动下一轮需求确认。" },
  ],
};

/** 兜底：未匹配阶段时用商务谈判 */
export const trainingGoals = stageTrainingGoals["商务谈判"];

/** 旧 goal 名 → 新展示名（历史数据 / 知识库 scenario 兼容） */
export const legacyGoalAliases = {
  线索获取: "线索判断",
  加微信: "建立连接",
  首次触达: "建立连接",
  首次拜访: "需求澄清",
  关键人确认: "再次推进",
  再次拜访: "再次推进",
  技术交涉: "方案讲解",
  报告讲解: "方案讲解",
  技术质疑: "异议应对",
  未通过复盘: "异议应对",
  价格异议: "价格异议",
  报价解释: "价格异议",
  条件谈判: "条件收口",
  成交推进: "条件收口",
  合同签订: "合同签订",
  订单交付: "交付确认",
  责任边界: "交付确认",
  回款交涉: "回款交涉",
  服务稳定: "关系维护",
  老客维护: "关系维护",
  复购推进: "复购推进",
  取得样品: "取得样品",
  试样推进: "试样推进",
  需求澄清: "需求澄清",
  约到拜访: "约到拜访",
  商机停滞: "条件收口",
};

/** 新展示名 → 写给后端/兼容旧知识库的 goal 名 */
export const displayToApiGoal = Object.fromEntries(
  Object.values(stageTrainingGoals)
    .flat()
    .map((goal) => [goal.name, goal.apiGoal || goal.name]),
);

export function normalizeGoalName(goal) {
  if (!goal) return "";
  return legacyGoalAliases[goal] || goal;
}

export function getStageGoals(stageName) {
  return stageTrainingGoals[stageName] || trainingGoals;
}

export function getRecommendedGoal(stageName) {
  const goals = getStageGoals(stageName);
  return (goals.find((item) => item.recommended) || goals[0]).name;
}

/** 切阶段后选目标：优先保留同名目标，否则用推荐项（不用下标 0） */
export function resolveGoalForStage(stageName, currentGoal) {
  const goals = getStageGoals(stageName);
  const normalized = normalizeGoalName(currentGoal);
  if (normalized && goals.some((item) => item.name === normalized)) {
    return normalized;
  }
  return getRecommendedGoal(stageName);
}

export function apiGoalFromDisplay(goalName) {
  const normalized = normalizeGoalName(goalName);
  return displayToApiGoal[normalized] || normalized;
}

// ---------------------------------------------------------------------------
// 客户维度：关系阶段 / 对接画像 / 难度 / 性格 / 关注点 —— 彼此正交，不要绑死。
// ---------------------------------------------------------------------------

/** 客户关系阶段（是否已有合作）—— 与价格敏感、性格无关 */
export const customerRelationshipOptions = [
  "陌拜新客户",
  "潜在新客户",
  "新成交客户",
  "老客户",
];

/** 对接角色 / 行业画像 —— 你在跟谁说话 */
export const customerPersonaOptions = [
  "印染加工厂·采购经理",
  "印染加工厂·技术主管",
  "印染加工厂·厂长",
  "面料生产厂·研发工程师",
  "面料生产厂·技术主管",
  "纺织外贸公司·采购经理",
  "纺织外贸公司·外贸经理",
];

export const customerDifficultyOptions = ["标准", "刁钻", "高压"];
export const customerPersonalityOptions = ["谨慎型", "压价型", "专业型", "敷衍型"];
export const customerConcernOptions = [
  "价格",
  "交期",
  "品质",
  "售后",
  "环保合规",
  "工艺适配",
  "供应稳定",
];

/** 目标 → 默认客户关系（仅强信号，可被用户改掉） */
const relationshipByGoal = {
  线索判断: "陌拜新客户",
  建立连接: "陌拜新客户",
  约到拜访: "陌拜新客户",
  需求澄清: "潜在新客户",
  取得样品: "潜在新客户",
  再次推进: "潜在新客户",
  方案讲解: "潜在新客户",
  试样推进: "潜在新客户",
  异议应对: "老客户",
  价格异议: "潜在新客户",
  条件收口: "潜在新客户",
  合同签订: "新成交客户",
  交付确认: "新成交客户",
  回款交涉: "老客户",
  关系维护: "老客户",
  复购推进: "老客户",
};

/** 仅这些目标会自动改客户关系，避免覆盖手选 */
export const strongRelationshipGoals = {
  陌拜新客户: ["线索判断", "建立连接", "约到拜访"],
  老客户: ["回款交涉", "关系维护", "复购推进", "异议应对"],
};

export function inferCustomerRelationship({ stage, goal, training_type } = {}) {
  const normalized = normalizeGoalName(goal);
  if (normalized && relationshipByGoal[normalized]) return relationshipByGoal[normalized];
  if (stage === "回款") return "老客户";
  if (stage === "了解商机") return "陌拜新客户";
  if (stage === "确认商机") return "潜在新客户";
  if (training_type === OPPORTUNITY_MODE && stage === "商务谈判") return "潜在新客户";
  return "潜在新客户";
}

export const trainingTemplates = [
  {
    id: "wet-rub-spot-complaint",
    template_id: "wet-rub-spot-complaint",
    title: "湿擦斑客诉",
    subtitle: "整批返修索赔，先归因不认赔",
    training_type: "客户情景陪练",
    stage: "方案论证",
    goal: "异议应对",
    customer_type: "老客户",
    customer_persona: "印染加工厂·技术主管",
    product_name: "湿摩擦牢度提升剂 833",
    product_need: "先定位出斑原因，再谈返修或换型",
    background:
      "珠三角针织染厂用湿擦后整批布出湿擦斑，客户要求退货并索赔返修费。现场是定型后布温高、工作液被带到40～50℃，又和固色剂同浴，水中金属离子偏多。日标测湿擦（压力2牛、曲面、磨100次），问题布约2.5级。要按望闻问切引导客户自查水质水温、布面残留、同浴固色和工作液温度四点，分清是工艺端还是产品端，再决定皂洗粉3～4g/L清洗、分浴处理，或换高稳定831B/868。",
    customer_difficulty: "高压",
    customer_personality: "专业型",
    customer_concern: "品质",
  },
  {
    id: "one-bath-process-conflict",
    template_id: "one-bath-process-conflict",
    title: "同浴工艺冲突",
    subtitle: "湿擦、固色、硅油想一浴过完",
    training_type: "客户情景陪练",
    stage: "方案论证",
    goal: "方案讲解",
    customer_type: "潜在新客户",
    customer_persona: "印染加工厂·技术主管",
    product_name: "湿摩擦牢度提升剂 868",
    product_need: "在不影响效率前提下把湿擦做到三级以上",
    background:
      "某校服单客户订单要求高，为降本增效想把湿擦、固色剂和硅油一浴过完，实测湿擦只有2～3级不达标。湿擦与固色剂易生成沉淀，部分硅油含阴离子稳定剂也会拉低稳定性。应推分步整理：先过一道湿擦约30g/L定型烘干，再固色剂与硅油同浴；若客户有双轧槽或轧槽加喷淋，可第一轧槽过湿擦、第二轧槽加硅油固色剂一步烘干。先问清设备条件，再定一步法还是两步法。",
    customer_difficulty: "刁钻",
    customer_personality: "专业型",
    customer_concern: "工艺适配",
  },
  {
    id: "phenol-free-compliance",
    template_id: "phenol-free-compliance",
    title: "无酚环保替代",
    subtitle: "品牌单要过 OEKO-TEX / GOTS",
    training_type: "客户情景陪练",
    stage: "方案论证",
    goal: "方案讲解",
    customer_type: "潜在新客户",
    customer_persona: "纺织外贸公司·采购经理",
    product_name: "无酚固色剂 HT-790",
    product_need: "替代有双酚风险的普通固色剂，保住品牌单",
    background:
      "客户接了品牌订单，要过蓝标、OEKO-TEX 或 GOTS，限制双酚A、壬基苯酚和甲醛，布面残留要求低于0.1甚至0.01。现用普通固色剂过不了审。推 HT-790：原液完全不含双酚、苯酚、对苯二酚、甲酚，可出原液报告；换用前必须彻底清洗染缸，避免旧助剂交叉污染。推荐用量3%（1%～5%提升力好），水洗汗渍基本四级，翠蓝荧光等敏感色色变小，印花白布防沾色好。客户若问布面为何还检出双酚，要从原液合规与缸体残留两条线解释。",
    customer_difficulty: "刁钻",
    customer_personality: "谨慎型",
    customer_concern: "环保合规",
  },
  {
    id: "lab-bulk-gap",
    template_id: "lab-bulk-gap",
    title: "大小样差异",
    subtitle: "小样三级大货二级半",
    training_type: "客户情景陪练",
    stage: "方案论证",
    goal: "异议应对",
    customer_type: "新成交客户",
    customer_persona: "面料生产厂·研发工程师",
    product_name: "湿摩擦牢度提升剂 833",
    product_need: "解释大小样差异并给出可执行补救方案",
    background:
      "客户小样按日标做到三级，大货只有二级半，质疑产品掺水要求退货。真实原因是大机同一缸水连续过布，后面的带液率比小样低，布面有效成分被稀释。常规用量约30g/L，可提到50～80g/L（返修布案例到80g/L才达标），或做二次定型：先过30g/L湿擦烘干，再湿擦与硅油同浴。要和客户对齐测试标准（日标2牛曲面 vs 国标/ISO 9牛）、取布位置和含水率，约定按同一条件重测。",
    customer_difficulty: "刁钻",
    customer_personality: "专业型",
    customer_concern: "品质",
  },
  {
    id: "hard-water-high-temp",
    template_id: "hard-water-high-temp",
    title: "水质高温选型",
    subtitle: "夏季水槽五六十度该换型号",
    training_type: "客户情景陪练",
    stage: "确认商机",
    goal: "需求澄清",
    customer_type: "潜在新客户",
    customer_persona: "印染加工厂·技术主管",
    product_name: "湿摩擦牢度提升剂 831B",
    product_need: "在高水温高硬度条件下稳定出湿擦效果",
    background:
      "客户厂里水槽建在楼顶，夏天直晒水温到五六十度，冷却水也有四五十度，地区水硬度偏高，偶尔还混用河水。他们一直用效果型833，天一热就破乳出斑。按望闻问切先问清水质、水温、工艺（浸轧/浸渍/喷淋）和布种：这类苛刻条件应改推高稳定性831B或868（浸轧浸渍皆可，牛仔定型也好），可提升3～4级；效果优先但水质一般的，才推8667。避免一上来就报833。",
    customer_difficulty: "标准",
    customer_personality: "谨慎型",
    customer_concern: "工艺适配",
  },
  {
    id: "cold-call-procurement",
    template_id: "cold-call-procurement",
    title: "电话陌拜",
    subtitle: "30 秒破冰约到微信",
    training_type: "客户情景陪练",
    stage: "了解商机",
    goal: "建立连接",
    customer_type: "陌拜新客户",
    customer_persona: "印染加工厂·采购经理",
    product_name: "固色剂 HT-766 / 亲水硅油",
    product_need: "破冰、摸清供应现状并约到微信或拜访",
    background:
      "从行业名录拿到珠三角某针织染厂采购电话，第一次联系。客户供应体系稳定，采购被同行频繁拜访，大概率会说「已经有稳定供应商了」。开场30秒自报家门：宏昊化工纺织助剂源头厂家，广东不少染厂在用我们固色剂和硅油，想了解贵司助剂是自选型还是有稳定供应商。禁用开场报价、贬低同行、一次塞满资料。有供应商就顺势加微信发目录留痕，再约15分钟带样品和工程师上门判断适配性。",
    customer_difficulty: "高压",
    customer_personality: "敷衍型",
    customer_concern: "供应稳定",
  },
  {
    id: "quality-hold-payment",
    template_id: "quality-hold-payment",
    title: "质量压款",
    subtitle: "以湿擦不达标为由拒付尾款",
    training_type: "客户情景陪练",
    stage: "回款",
    goal: "回款交涉",
    customer_type: "老客户",
    customer_persona: "印染加工厂·采购经理",
    product_name: "湿摩擦牢度提升剂 8667",
    product_need: "质量争议与付款义务分开收口",
    background:
      "老客户某批货以湿擦不达标为由拒付尾款，扬言先解决质量再谈钱。出货前有质检报告和留样，工艺端疑似同浴固色、水质偏硬或大机带液率偏低导致。按回款要点先对账、再对质：质量和付款两件事分开推进，用报告与留样数据说话，一起复盘工艺条件；同时把「尽快付」逼成明确日期或分期节点，书面留痕。禁用威胁停货、越过采购找老板、混谈减免。",
    customer_difficulty: "刁钻",
    customer_personality: "压价型",
    customer_concern: "品质",
  },
  {
    id: "ht766-same-bath-intro",
    template_id: "ht766-same-bath-intro",
    title: "同浴固色剂推介",
    subtitle: "锦纶无缝内衣染固同浴省水省时",
    training_type: "客户情景陪练",
    stage: "方案论证",
    goal: "方案讲解",
    customer_type: "潜在新客户",
    customer_persona: "面料生产厂·技术主管",
    product_name: "同浴固色剂 HT-766",
    product_need: "缩短固色流程并保住泡水、水洗牢度",
    background:
      "锦纶无缝内衣厂现在染色后还要走3～4道固色，流程长、耗水多、加工成本高。推 HT-766 中性酸性固色剂，同浴不需调酸：80℃加固色剂和匀染剂升到98℃染固30～60分钟；或染后不排液，降温到80℃加药运行10～20分钟。工厂大试泡水4级、水洗3级以上，无缝内衣同浴省约两缸水，每吨布省几百元。对比市售竞品牢度与性价比都有优势。客户常担心敏感色（灰）色变、残液偏深——色变靠工艺修色，残液建议搭配匀染剂 TY1。",
    customer_difficulty: "标准",
    customer_personality: "专业型",
    customer_concern: "工艺适配",
  },
  {
    id: "new-mill-visit",
    template_id: "new-mill-visit",
    title: "新厂陌拜",
    subtitle: "新投产染厂供应商未定型",
    training_type: OPPORTUNITY_MODE,
    stage: "了解商机",
    goal: "约到拜访",
    customer_type: "陌拜新客户",
    customer_persona: "印染加工厂·厂长",
    product_name: "前处理助剂 / 固色剂 / 湿摩擦牢度提升剂",
    product_need: "建立源头厂家形象并约到首次拜访",
    background:
      "肇庆新投产针织染厂，供应商尚未定型，同行已开始接触。技术负责人话语权大，关注产品稳定性、技术指导和能否快速配合试样。通过行业朋友转介绍拿到入口，目标是把线上接触推进到一次15分钟上门：带样品和技术工程师，现场判断适配性，并留下免费试样钩子。",
    last_contact: "通过转介绍获得联系方式，尚未正式接触。",
    decision_blocker: "关键人未参与",
    next_milestone: "约到首次拜访",
    stakeholder: "暂无直接联系人，厂长、技术主管与采购的决策关系未知",
    customer_difficulty: "标准",
    customer_personality: "敷衍型",
    customer_concern: "供应稳定",
  },
  {
    id: "overseas-bluesign",
    template_id: "overseas-bluesign",
    title: "海外蓝标客户",
    subtitle: "蓝标 / GOTS 合规与高温水质选型",
    training_type: OPPORTUNITY_MODE,
    stage: "方案论证",
    goal: "方案讲解",
    customer_type: "潜在新客户",
    customer_persona: "纺织外贸公司·外贸经理",
    product_name: "湿摩擦牢度提升剂 868",
    product_need: "在高温水质下稳定过出口环保与牢度标准",
    background:
      "海外牛仔/品牌单客户所在地区水温常到五六十度，水质偏硬，以前用的湿擦产品容易破乳。客户同时卡 bluesign、GOTS 和 OEKO-TEX，要求提供认证与测试依据。868 闪点约70°、已通过蓝标，浸轧浸渍皆可用、牛仔定型效果好，适合这类苛刻条件；固色可配套无醛固色剂 HT-5095 或无酚 HT-790。讲解时先对齐测试标准（日标2牛曲面 vs 国标/ISO/美标9牛），再给认证文件、对比报告和送样计划。",
    last_contact: "已发产品清单和蓝标资料，但测试标准与送样条件尚未对齐。",
    decision_blocker: "样品或测试未完成",
    next_milestone: "取得样品或测试条件",
    stakeholder: "外贸经理已沟通，品牌端标准确认人还未参与",
    customer_difficulty: "刁钻",
    customer_personality: "谨慎型",
    customer_concern: "环保合规",
  },
];

/** 新词表优先，旧 goal 名作别名回退 */
export const standardReplies = {
  线索判断: "我想先确认一下贵司当前是否真的有替换或新增供应的需求。方便的话，我们先对齐使用场景、当前供应痛点和预计推进时间，再判断是否值得进入下一步。",
  建立连接: "您好，我是宏昊化工的小陈，我们是纺织助剂源头厂家，广东这边不少染厂在用我们的固色剂和硅油。今天冒昧打过来，想先了解贵司助剂这块是自己选型，还是已经有稳定供应商了？",
  约到拜访: "为了不只停留在资料沟通，我建议约一次15分钟的简短拜访，带上样品和技术工程师，把使用场景、工艺条件和关键关注点一次性确认清楚。",
  需求澄清: "我先不急着推荐型号，想确认四个问题：水质和水温怎么样、工艺是浸轧还是浸渍、布种和牢度要求是什么、这次评估由谁来判断是否通过。",
  取得样品: "如果要判断方案是否适配，最好先拿到样品或工艺条件。您看我们是否可以先确认样品规格和测试标准？",
  再次推进: "上次沟通后还有几个点没有收口，我建议再约一次，把样品、测试条件和下一步责任人明确下来。",
  方案讲解: "这个问题我建议用测试条件来对齐。您方便把当前工艺参数和评判标准发我吗？我会按同一标准给出对比说明和样品验证建议。",
  异议应对: "质量责任我们先不急着下结论。这批货出货前有质检报告和留样，建议先一起复盘水质水温、同浴加料和带液率这些工艺条件，确认原因后再谈返修或换型，这样对双方都更公平。",
  试样推进: "现在关键不是继续讨论概念，而是把试样条件、评判标准和反馈时间定下来。您看这周能否先安排一次试样确认？",
  价格异议: "我理解您对价格敏感。我们先不急着谈降价，我想先和您确认三件事：稳定性损耗、交付周期风险，以及这次测试通过后能否进入下一步技术确认。",
  条件收口: "价格可以谈，但我希望和交付周期、账期、质量责任一起确认，避免只压单价却把后续风险放大。",
  合同签订: "我们可以先把合同里最容易反复的价格、交付、质量和责任边界确认掉，避免后面影响订单执行。",
  交付确认: "订单交付我建议先确认时间、质量标准和异常响应方式，这样双方后续执行会更稳。",
  回款交涉: "质量和付款是两件事，我建议分开推进。这批货我们可以先一起复盘工艺和使用条件；同时请您确认这笔款项的付款节点，两边都不耽误。",
  关系维护: "回款和复购都和服务体验有关。我想先确认最近服务里最影响贵司判断的问题，再一起定一个恢复稳定的动作。",
  复购推进: "如果前期服务和交付没有问题，我们可以一起看下一轮需求计划，先确认时间、规格和可能的备货安排。",
  // 旧名兼容
  首次触达: "您好，我是宏昊化工的小陈，我们是纺织助剂源头厂家，广东这边不少染厂在用我们的固色剂和硅油。今天冒昧打过来，想先了解贵司助剂这块是自己选型，还是已经有稳定供应商了？",
  技术交涉: "这个问题我建议用测试条件来对齐。您方便把当前工艺参数和评判标准发我吗？我会按同一标准给出对比说明和样品验证建议。",
  技术质疑: "质量责任我们先不急着下结论。这批货出货前有质检报告和留样，建议先一起复盘水质水温、同浴加料和带液率这些工艺条件，确认原因后再谈返修或换型，这样对双方都更公平。",
  未通过复盘: "试样没有通过没关系，我们先把原因拆清楚：是大小样带液率差异、工艺条件、样品匹配，还是操作过程影响。确认后再决定是加量、二次定型还是重新打样。",
  报告讲解: "这份报告我想重点和您对齐三点：测试条件是否一致（日标还是国标）、关键指标差异在哪里、这些差异会怎样影响稳定性和返修成本。",
  条件谈判: "价格可以谈，但我希望和交付周期、账期、质量责任一起确认，避免只压单价却把后续风险放大。",
  报价解释: "这次报价里不只是单价，还包含稳定性、交付响应和后续服务成本。我们可以先看总使用成本，再判断是否还有调整空间。",
  成交推进: "目前信息已经比较完整，我建议把下一步收敛成一个明确动作：确认关键人、确认条件，或者约定合同节点。",
  订单交付: "订单交付我建议先确认时间、质量标准和异常响应方式，这样双方后续执行会更稳。",
  责任边界: "为了避免后续扯皮，我们先明确双方责任人、交付节点、验收标准和异常处理方式。",
  服务稳定: "回款和复购都和服务体验有关。我想先确认最近服务里最影响贵司判断的问题，再一起定一个恢复稳定的动作。",
  老客维护: "我想先复盘最近订单减少的真实原因，是价格、库存、交付还是服务体验。确认原因后，我们再一起定一个恢复采购的动作。",
  商机停滞: "我担心这个项目现在卡在下一步责任人不清晰。我们能不能先约一次 20 分钟沟通，把技术、采购和测试条件一次性确认下来？",
  关键人确认: "这件事后续会涉及采购、技术和使用端判断。为了避免来回传话，我们能否把关键评估人一起拉进下一次沟通？",
  再次拜访: "上次沟通后还有几个点没有收口，我建议再约一次，把样品、测试条件和下一步责任人明确下来。",
  首次拜访: "我先不急着推荐型号，想确认四个问题：水质和水温怎么样、工艺是浸轧还是浸渍、布种和牢度要求是什么、这次评估由谁来判断是否通过。",
};

export const defaultForm = {
  training_type: "客户情景陪练",
  stage: "商务谈判",
  goal: "价格异议",
  owner_name: "陈宇",
  customer_name: "清远某针织染厂",
  customer_type: "潜在新客户",
  customer_persona: "印染加工厂·采购经理",
  product_name: "HT-790 无酚固色剂",
  product_need: "品牌单环保合规，色牢度要稳定",
  background:
    "客户是清远一家针织染厂，接了品牌订单要过 OEKO-TEX，现用固色剂有双酚风险。采购嫌报价偏高，技术主管要看原液报告和布面残留数据，希望先小样对比再谈采购量。",
  last_contact: "已发 HT-790 原液报告和推荐用量3%，约定本周安排小样对比。",
  decision_blocker: "关键人未参与",
  next_milestone: "约到关键人会议",
  stakeholder: "采购已参与，技术负责人还未确认残留指标",
  customer_difficulty: "标准",
  customer_personality: "谨慎型",
  customer_concern: "环保合规",
  template_id: "",
};
