"use client";

import { cn } from "@/lib/cn";

export interface LikertProps {
  scale: { min: number; max: number; minLabel: string; maxLabel: string };
  value: number | undefined;
  onChange: (v: number) => void;
  name?: string;
}

export function Likert({ scale, value, onChange, name }: LikertProps) {
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
            className={cn("likert-cell", value === p && "likert-cell-active")}
          >
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
