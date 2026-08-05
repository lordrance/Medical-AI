"use client";

/**
 * 李克特量表（Likert scale）—— 就是「1 到 5 选一个」的那排按钮。
 *
 * 全站所有量表题都用它：前测、后测 40 多道、每道案例后的 2 道小量表。
 * 只写一次，样式和交互全站一致。
 */

import { cn } from "@/lib/cn";

export interface LikertProps {
  /** 刻度范围和两端的文字标签，如 1~5 / "非常不同意" ~ "非常同意"。 */
  scale: { min: number; max: number; minLabel: string; maxLabel: string };
  value: number | undefined;   // 当前选中的分数，undefined = 还没选
  onChange: (v: number) => void;
  /** 单选组的名字。★ 必须传且各题不同，否则同一页多道题会互相干扰
   *  （浏览器认为同名的 radio 是一组，选了这道另一道就被取消）。 */
  name?: string;
}

export function Likert({ scale, value, onChange, name }: LikertProps) {
  // 由 min/max 生成分数数组。1~5 → [1,2,3,4,5]
  const points = Array.from(
    { length: scale.max - scale.min + 1 },
    (_, i) => scale.min + i,
  );
  return (
    <div>
      <div className="flex items-center gap-1.5">
        {points.map((p) => (
          <label
            key={p}
            // 选中的那个加高亮样式
            className={cn("likert-cell", value === p && "likert-cell-active")}
          >
            {/* ★ 用真正的 radio 而不是 div 模拟，只是把它视觉上藏起来
                （sr-only = 屏幕阅读器可见、肉眼不可见）。
                这样键盘操作、读屏软件、表单语义全都自动正确。 */}
            <input
              type="radio"
              name={name}
              className="sr-only"
              checked={value === p}
              onChange={() => onChange(p)}
            />
            <span className="text-sm font-semibold leading-none">{p}</span>
          </label>
        ))}
      </div>
      <div className="mt-1.5 flex justify-between text-[11px] text-muted-foreground">
        <span>{scale.minLabel}</span>
        <span>{scale.maxLabel}</span>
      </div>
    </div>
  );
}
