// Survey schema lives in the backend (`backend/data/pre_survey.json`).
// We keep a hand-mirror here for the form UI; identical id values must match
// what the backend's /api/pre-survey expects.

export interface SurveyItem {
  id: string;
  type: "select" | "number" | "multi_select" | "likert";
  label: string;
  required?: boolean;
  options?: string[];
  min?: number;
  max?: number;
  scale?: { min: number; max: number; minLabel: string; maxLabel: string };
}

export interface SurveyConfig {
  title: string;
  description: string;
  items: SurveyItem[];
}

export const preSurveyConfig: SurveyConfig = {
  title: "前测问卷",
  description: "在开始审核案例之前，请回答以下背景问题（约 2—3 分钟）。",
  items: [
    {
      id: "pre_specialty",
      type: "select",
      required: true,
      label: "您的主要科室 / 专科是什么？",
      options: [
        "心血管内科",
        "呼吸内科",
        "消化内科",
        "内分泌科",
        "肾内科",
        "神经内科",
        "血液内科",
        "风湿免疫科",
        "感染科",
        "普通外科",
        "骨科",
        "神经外科",
        "胸外科",
        "泌尿外科",
        "心脏外科",
        "整形外科",
        "妇产科",
        "儿科",
        "急诊医学科",
        "全科医学科",
        "重症医学科",
        "麻醉科",
        "影像科",
        "检验科",
        "病理科",
        "中医科",
        "中西医结合",
        "其他",
      ],
    },
    {
      id: "pre_training_level",
      type: "select",
      required: true,
      label: "您当前的培训层级是什么？",
      options: [
        "医学生（本科 / 硕士 / 博士）",
        "规培住院医师（一阶段）",
        "规培住院医师（二阶段 / 专培）",
        "主治医师",
        "副主任医师",
        "主任医师",
      ],
    },
    {
      id: "pre_years_post_residency",
      type: "number",
      required: true,
      label: "您完成住院医培训后有几年工作年资？（如果仍在培训中请填 0）",
      min: 0,
      max: 60,
    },
    {
      id: "pre_weekly_msg_volume",
      type: "select",
      required: true,
      label:
        "您平均每周需要处理多少条线上患者的消息？同一位患者连续发送多条消息时，请按一条计算。",
      options: ["0", "1—10 条", "11—25 条", "26—50 条", "51—100 条", "100 条以上"],
    },
    {
      id: "pre_ai_drafting_familiarity",
      type: "likert",
      required: true,
      label: "您对生成式 AI 起草工具的熟悉程度如何？",
      scale: {
        min: 1,
        max: 5,
        minLabel: "完全不熟悉，从未使用过",
        maxLabel: "非常熟悉且有较多使用经验",
      },
    },
  ],
};
