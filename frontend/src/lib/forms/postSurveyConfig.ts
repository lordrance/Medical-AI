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

/** 与 `backend/data/post_survey.json` 保持 id/文案一致。 */
export const postSurveyConfig: PostSurveyConfig = {
  "title": "后测问卷",
  "description": "感谢您完成案例审核。请根据您的真实感受作答（约 10—15 分钟）。",
  "scale": {
    "min": 1,
    "max": 5,
    "minLabel": "非常不同意",
    "maxLabel": "非常同意"
  },
  "blocks": [
    {
      "id": "digital_efficiency",
      "title": "A. AI 与数字效能",
      "items": [
        {
          "id": "pre_ai_readiness_1",
          "text": "学习使用新的临床数字工具通常会让我感到费力。"
        },
        {
          "id": "pre_ai_readiness_2",
          "text": "我通常可以在没有他人帮助的情况下学会使用新的临床软件或应用。"
        },
        {
          "id": "pre_ai_readiness_3",
          "text": "我在生活或工作中已经有使用 AI 工具的习惯。"
        },
        {
          "id": "pre_ai_readiness_4",
          "text": "接触新的 AI 或数字工具时，我通常愿意花时间主动摸索它的功能。"
        }
      ]
    },
    {
      "id": "utility",
      "title": "B. 感知有用性 / 工具效用",
      "items": [
        {
          "id": "post_utility_1",
          "text": "此类 AI 工具在临床文本工作中具有实际参考价值。"
        },
        {
          "id": "post_utility_2",
          "text": "AI 生成内容能为我的临床回复提供新的思路。"
        },
        {
          "id": "post_utility_3",
          "text": "AI 生成内容有助于我检查回复是否覆盖患者主要关切。"
        },
        {
          "id": "post_utility_4",
          "text": "我更认可此类 AI 工具在组织语言和信息方面的作用，而不是在形成临床判断方面的作用。"
        }
      ]
    },
    {
      "id": "transparency",
      "title": "C. 信息来源判断与透明度",
      "items": [
        {
          "id": "post_transparency_1",
          "text": "AI 生成内容中，事实和推断内容有时不容易区分。"
        },
        {
          "id": "post_transparency_2",
          "text": "我有时难以判断 AI 生成内容中的某些说法是否有足够依据。"
        },
        {
          "id": "post_transparency_3",
          "text": "我判断 AI 生成内容时，需要看到更清楚的来源或依据提示。"
        }
      ]
    },
    {
      "id": "comm",
      "title": "D. 医患互动与沟通",
      "items": [
        {
          "id": "post_comm_1",
          "text": "我认为 AI 辅助起草或修改临床内容可以提高医患沟通效率。"
        },
        {
          "id": "post_comm_2",
          "text": "我担心患者得知回复使用过 AI 辅助后，会降低对医生回复的信任。"
        },
        {
          "id": "post_comm_3",
          "text": "使用 AI 生成内容时，我愿意花更多精力把回复调整成自己的沟通风格。"
        },
        {
          "id": "post_comm_4",
          "text": "我认为患者可见的 AI 修改或编辑记录，有助于提高患者对临床回复的信任。"
        }
      ]
    },
    {
      "id": "burden",
      "title": "E. 认知负担、审核压力与身体疲劳",
      "items": [
        {
          "id": "post_burden_1",
          "text": "审核 AI 生成内容时，我需要花较多精力判断哪些内容应保留、修改或删除。"
        },
        {
          "id": "post_burden_2",
          "text": "使用 AI 起草工具时，我会对最终回复保持额外谨慎，并感到一定审核压力。"
        },
        {
          "id": "post_burden_3",
          "text": "在 AI 生成内容、病历信息和最终回复之间来回切换，会增加我的操作负担。"
        }
      ]
    },
    {
      "id": "governance",
      "title": "F. 数据治理、责任归属与临床监督",
      "items": [
        {
          "id": "post_governance_1",
          "text": "我目前不清楚 AI 生成内容出错后，主要责任应如何划分。"
        },
        {
          "id": "post_governance_2",
          "text": "我担心患者数据进入 AI 工具后，后续如何被使用或保存并不透明。"
        },
        {
          "id": "post_governance_3",
          "text": "我担心 AI 生成内容经过系统、机构和医生共同参与后，最终责任仍会集中到最后审核或发送的医生身上。"
        },
        {
          "id": "post_governance_4",
          "text": "我担心相关机构在推动 AI 使用时，没有同步说明医生应如何审核、记录或拒用 AI 生成内容。"
        }
      ]
    },
    {
      "id": "reliance",
      "title": "G. AI 依赖调节与过度依赖风险",
      "items": [
        {
          "id": "post_reliance_1",
          "text": "时间压力会影响我核查和修改 AI 生成内容的深度。"
        },
        {
          "id": "post_reliance_2",
          "text": "AI 生成回复的整体框架和思路，往往会成为我思考最终回复内容的起点。"
        },
        {
          "id": "post_reliance_3",
          "text": "长期使用此类工具可能会影响我发现异常信息或不合理建议的敏感度。"
        },
        {
          "id": "post_reliance_4",
          "text": "我担心自己在临床文本工作中会逐渐过度依赖 AI 生成内容。"
        }
      ]
    },
    {
      "id": "hallu",
      "title": "H. AI 幻觉与准确性风险",
      "items": [
        {
          "id": "post_hallu_1",
          "text": "我感觉 AI 生成内容有时会补出病历中没有直接支持的信息。"
        },
        {
          "id": "post_hallu_2",
          "text": "我感觉 AI 生成内容有时会基于有限信息，给出超出证据支持范围的临床判断。"
        },
        {
          "id": "post_hallu_3",
          "text": "我担心 AI 生成内容会把风险程度、紧急程度或建议强度表达得不够准确。"
        },
        {
          "id": "post_hallu_4",
          "text": "我感觉 AI 生成内容有时会遗漏或弱化需要提醒患者注意的关键信息。"
        }
      ]
    },
    {
      "id": "attention",
      "title": "注意力检测",
      "items": [
        {
          "id": "attn_post_1",
          "text": "为确认您在认真作答，请在本题选择「4」。"
        }
      ]
    },
    {
      "id": "calibration",
      "title": "I. 可靠性感知与采用边界判断",
      "items": [
        {
          "id": "post_calibration_1",
          "text": "对我来说，在不同临床文本任务中判断 AI 生成内容是否可用，并不总是容易。"
        },
        {
          "id": "post_calibration_2",
          "text": "我在使用 AI 生成内容时，往往需要进行较大幅度的修改。"
        },
        {
          "id": "post_calibration_3",
          "text": "对于方向基本正确但仍需补充或调整的 AI 生成内容，我有时难以决定应采用多少。"
        }
      ]
    },
    {
      "id": "dissent",
      "title": "AI 分歧反馈与认知审视",
      "items": [
        {
          "id": "post_dissent_1",
          "text": "当 AI 生成的内容与我的初步临床判断存在分歧时，我愿意停下来重新审视自己的想法。"
        },
        {
          "id": "post_dissent_2",
          "text": "我希望 AI 能够主动指出我草拟回复中可能存在的漏洞或思维盲区，哪怕这会打断我的工作流。"
        },
        {
          "id": "post_dissent_3_reverse",
          "text": "当 AI 提出与我不同的临床意见时，我更倾向于坚持自己的判断，而不是进一步查看 AI 的依据。"
        }
      ]
    },
    {
      "id": "accept",
      "title": "K. 未来使用倾向与接受信任",
      "items": [
        {
          "id": "post_accept_trust",
          "text": "我对 AI 起草工具在临床文本工作中的辅助作用持信任态度。"
        },
        {
          "id": "post_accept_future_use",
          "text": "我未来愿意在真实临床文本工作中使用此类 AI 起草工具。"
        },
        {
          "id": "post_accept_limited_use",
          "text": "我只愿意在部分临床文本任务中试用此类 AI 工具。"
        },
        {
          "id": "post_accept_optional",
          "text": "我倾向于把此类 AI 工具作为可选择的工作支持，而不是固定流程。"
        }
      ]
    }
  ]
} as PostSurveyConfig;
