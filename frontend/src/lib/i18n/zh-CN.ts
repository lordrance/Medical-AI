// Chinese (Simplified) UI dictionary. Keep UI text out of components.
export const zh = {
  nav: {
    back: "返回",
  },
  app: {
    title: "AI 草稿审核研究平台",
    subtitle: "脚本化 HCI 实验平台 · 不提供医疗服务",
    footer: "本系统仅用于科研目的 · v0.2",
  },
  home: {
    welcome: "欢迎参与本研究",
    intro:
      "您将在大约 30 分钟内审核若干虚构的患者消息及对应的 AI 草稿回复，并决定如何处理。所有案例均为虚构，不涉及真实病例与病人信息。",
    notMedical:
      "本平台不是临床医疗服务，AI 草稿仅作为研究素材，不应作为任何真实诊疗依据。",
    start: "开始研究",
  },
  consent: {
    title: "知情同意",
    p1: "您将审核若干虚构的患者消息以及 AI 起草的回复，并对每条作出处理决定。本研究不涉及任何真实病例信息。",
    p2: "我们将记录您的审核选择、最终回复文本、点击事件与时长。所有数据按假名 ID 脱敏存储，仅用于学术研究。",
    p3: "您可以随时关闭页面退出研究。完成研究后会显示一个完成码（completion code）。",
    checklistIntro:
      "在审核每条 AI 草稿时，请您自行留意以下核查角度（正式案例中不再逐条列出清单）：",
    checklistBullets: [
      "所选处理方式与患者风险程度是否匹配（含是否需升级或线下评估）。",
      "回复是否避免无依据的安抚，并包含必要的安全网与红旗症状提示。",
      "药物与过敏史、病历摘要是否一致，是否存在与记录矛盾或证据不足之处。",
    ],
    agree: "我已阅读上述内容，同意参与本研究",
    cta: "我同意 — 开始",
    starting: "正在创建研究会话…",
    failed: "无法启动研究",
  },
  preSurvey: {
    submit: "继续",
    saving: "正在保存…",
  },
  practice: {
    banner:
      "练习案例 — 让您熟悉界面布局、四种处理动作以及案例后的三道小题。本案例不计入主分析。",
  },
  caseUI: {
    progress: (i: number, n: number) => `案例 ${i} / ${n}`,
    practice: "练习案例",
    caseIdLabel: "案例编号",
    formalProgressHint: (i: number, n: number) => `正式进度：第 ${i} 题 / 共 ${n} 题`,
    practiceProgressHint: "练习案例（不计入正式进度）",
    condition: (c: string) =>
      c === "guardrail"
        ? "实验组：护栏界面（含 AI 总结与 AI 风险提示）"
        : "对照组：不展示护栏区（仅患者消息、病历摘要与 AI 草稿）",
    patientMessage: "患者消息",
    chartSnapshot: "病历摘要",
    chartExpand: "展开病历摘要",
    chartCollapse: "收起病历摘要",
    aiDraft: "AI 起草的回复",
    sendAsIsAckLabel:
      "原样发送前请确认：我已核对 AI 草稿与病历摘要等信息，再决定是否发送。",
    sendAsIsAckRequired: "若选择原样发送，请先勾选上述核对确认。",
    guardrailTitle: "护栏面板（仅本组可见）",
    factsUsed: "AI 总结",
    riskCue: "AI 风险提示",
    checklist: "核查清单",
    actionsHeading: "请选择处理方式",
    finalReplyLabel: "最终回复内容",
    finalReplyHelpEdit: "已用 AI 草稿预填，可在此基础上修改",
    finalReplyHelpRewrite: "请重新撰写最终回复",
    chars: (n: number) => `${n} 字`,
    saveAndContinue: "保存并继续",
    saving: "保存中…",
    pickAction: "请先选择一种处理方式",
    fillReply: "请填写最终回复",
    quickHeading: "请回答以下三道小题",
    quickContinue: "继续下一案例",
  },
  actions: {
    send_as_is: { label: "原样发送", hint: "不修改 AI 草稿，原样发送给患者" },
    edit_then_send: { label: "编辑后发送", hint: "在 AI 草稿基础上做修改后再发送" },
    discard_and_rewrite: { label: "弃用并重写", hint: "弃用 AI 草稿，自行重新撰写" },
    escalate: { label: "升级处理", hint: "本消息不宜按普通在线问诊回复处理" },
  },
  escalateSubtype: {
    label: "升级处理类型",
    options: {
      "": "—",
      urgent_evaluation: "建议立即就诊或急诊",
      call_patient: "电话回访患者",
      other: "其他升级处理",
    },
  },
  escalateReason: {
    label: "请说明升级处理的原因",
    placeholder: "例如：存在气道风险需紧急评估、与过敏史冲突、需电话澄清等",
    required: "请填写升级原因后再提交",
  },
  scale: {
    minLabel: "非常不同意",
    maxLabel: "非常同意",
  },
  postSurvey: {
    submit: "提交问卷",
    saving: "提交中…",
  },
  completion: {
    title: "感谢您的参与",
    body: "您的回答已成功提交，可以关闭此页面了。如果招募方需要您回填完成码，请将下方编码原样填写。",
    code: "完成码",
    performanceTitle: "本次审核表现小结",
    performanceLine: (correct: number, total: number, pct: string) =>
      `正式案例共 ${total} 题，答对 ${correct} 题，准确率 ${pct}。`,
    performanceHint:
      "「答对」指所选处理方式与研究团队预设的参考标准一致；练习案例不计入。",
    reset: "重置（仅调试）",
  },
  admin: {
    title: "管理员后台",
    needToken: "请在 URL 后追加 ?token=您的ADMIN_TOKEN 后访问。",
    loading: "正在加载…",
    completion: "完成情况",
    completionLine: (a: number, b: number) => `已完成 ${a} / ${b}`,
    confusion: "混淆矩阵",
    confusionHint: "行 = 标准答案主选项（gold action）；列 = 医生选择。整体准确率：与 gold 或 goldActionAlternates 任一一致即计为正确。",
    matchGoldOrAlt: "金标准一致",
    matchGoldOnly: "仅主 gold",
    matchAltOnly: "仅备选",
    accuracy: "整体准确率",
    perCase: "按案例统计",
    perParticipant: "按参与者统计",
    download: "下载数据",
    exportFullDb: "整库 SQL 导出",
    exportFullDbHint:
      "SQLite：文本 SQL；PostgreSQL：需服务器安装 pg_dump。用于完整备份或在本地还原全部表。",
    exportBundle: "研究数据 ZIP（多表 CSV）",
    exportBundleHint:
      "默认包含参与者、会话、呈现、动作、问卷、UI 事件、案例内容、顺序模板、LLM 审计、总结表及 summary。可用 tables= 参数节选。",
    csv: "CSV",
    json: "JSON",
    llmHeading: "AI 自然语言总结",
    llmDisabledHint:
      "当前 LLM 未启用。请在后端 .env 设置 LLM_PROVIDER=deepseek 并配置 DEEPSEEK_API_KEY 后重启。",
    llmGenerateCohort: "生成本次实验中文总结",
    llmGenerating: "正在调用 LLM…",
    llmError: "调用失败",
  },
  errors: {
    network: "网络异常，请稍后重试",
    unknown: "出现未知错误",
  },
} as const;

export type I18nDict = typeof zh;
