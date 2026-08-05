// Survey schema lives in the backend (`backend/data/pre_survey.json`).
// We keep a hand-mirror here for the form UI; identical id values must match
// what the backend's /api/pre-survey expects.
//
// ★ 中文：前测问卷的题目内容。改题目改这里。
//
// 和后测的区别：前测的答案会存进 participants 表的**独立列**
//（pre_specialty、pre_training_level…），因为这几项是分析时最常用来
// 分组的变量，做成列比塞进 JSON 更好查。
// 所以这里的 id **必须**和 backend/app/api/survey.py 里 _str(a, "xxx")
// 取的键名完全一致，改了名后端就读不到，那一列会变成空。

/** 一道前测题。前测的题型比后测多，因为要采集科室、年资这类结构化信息。 */
export interface SurveyItem {
  id: string;
  type: "select" | "number" | "multi_select" | "likert";  // 下拉 / 数字 / 多选 / 量表
  label: string;
  required?: boolean;   // 必答题会显示红色星号，且不填就不能提交
  options?: string[];   // select / multi_select 的选项
  min?: number;         // number 类型的取值范围
  max?: number;
  scale?: { min: number; max: number; minLabel: string; maxLabel: string };  // likert 的刻度
}

export interface SurveyConfig {
  title: string;
  description: string;
  items: SurveyItem[];  // 前测题少，不像后测那样还要分组
}

export const preSurveyConfig: SurveyConfig = {
  title: "前测问卷",
  description: "在开始审核案例之前，请回答以下背景问题。",
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
      label: "您对生成式 AI 起草工具（例如豆包、DeepSeek、ChatGPT、Kimi 等）的熟悉程度如何？",
      scale: {
        min: 1,
        max: 5,
        minLabel: "完全不熟悉，从未使用过",
        maxLabel: "非常熟悉且有较多使用经验",
      },
    },
  ],
};
