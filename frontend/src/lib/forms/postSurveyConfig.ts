export interface PostSurveyItem {
  id: string;
  type?: "likert" | "text";
  text: string;
}
export interface PostSurveyBlock {
  id: string;
  title: string;
  items: PostSurveyItem[];
}
export interface PostSurveyConfig {
  title: string;
  description: string;
  scale: { min: number; max: number; minLabel: string; maxLabel: string };
  blocks: PostSurveyBlock[];
}

export const postSurveyConfig: PostSurveyConfig = {
  title: "后测问卷",
  description:
    "感谢您完成案例审核。请回答以下关于您对 AI 起草工具整体看法的问题，约 6—8 分钟。",
  scale: { min: 1, max: 7, minLabel: "非常不同意", maxLabel: "非常同意" },
  blocks: [
    {
      id: "trust",
      title: "信任",
      items: [
        { id: "trust_1", text: "我信任 AI 起草的内容是临床上合理的初稿。" },
        { id: "trust_2", text: "我可以接受在快速审阅之后就把 AI 草稿发送给患者。" },
        { id: "trust_3", text: "AI 起草工具大体上能抓住最关键的问题。" },
      ],
    },
    {
      id: "transparency",
      title: "透明度 / 可解释性",
      items: [
        { id: "transparency_1", text: "我能清楚地看出 AI 在起草回复时使用了哪些信息。" },
        { id: "transparency_2", text: "我能识别出 AI 在某些情况下其实并不确定或证据较弱。" },
        { id: "transparency_3", text: "我能识别出 AI 的推理与病历内容不匹配的情况。" },
      ],
    },
    {
      id: "workflow_fit",
      title: "工作流契合 / 负担",
      items: [
        { id: "workflow_1", text: "在这种界面下审核 AI 草稿可以融入我的日常工作流。" },
        { id: "workflow_2", text: "审核 AI 草稿比从头写回复更省力。" },
        { id: "workflow_3", text: "这种界面让我做决策时的认知负担变重了。" },
      ],
    },
    {
      id: "accountability",
      title: "责任 / 边界",
      items: [
        { id: "accountability_1", text: "作为审核者的我，应当为最终发送给患者的内容负主要责任。" },
        { id: "accountability_2", text: "如果 AI 草稿存在错误而我直接发送了，我应当承担主要责任。" },
        { id: "accountability_3", text: "在这种工作流中，临床医生与 AI 工具之间的责任边界是清晰的。" },
      ],
    },
    {
      id: "overreliance_concern",
      title: "过度依赖担忧",
      items: [
        { id: "overreliance_1", text: "我担心同行临床医生可能会过度依赖 AI 起草工具。" },
        { id: "overreliance_2", text: "我担心我自己也可能在某些情况下过度依赖 AI 草稿。" },
        { id: "overreliance_3", text: "时间压力可能会让医生在没有充分审核的情况下就发送 AI 草稿。" },
      ],
    },
    {
      id: "open_ended",
      title: "开放题（可选）",
      items: [
        { id: "open_1", type: "text", text: "如果增加哪些功能，会最大程度帮助您安全地审核 AI 草稿？" },
        { id: "open_2", type: "text", text: "其他对本次体验的反馈或建议（可选）" },
      ],
    },
  ],
};
