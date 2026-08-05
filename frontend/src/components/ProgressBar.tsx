/**
 * 答题进度条。显示在每道题的顶部，如「第 3 / 8 题」。
 *
 * 作用不只是好看：让医生知道「还剩几道」能显著降低中途放弃率——
 * 看不到头的问卷最容易被关掉。
 */

interface Props {
  current: number;
  total: number;
  label?: string;
}

export function ProgressBar({ current, total, label }: Props) {
  // 算百分比，并夹在 0~100 之间。
  // Math.max(total, 1) 防止除以零；外面的 max/min 防止传进来奇怪的值
  // （比如 current > total）导致进度条溢出容器。
  const pct = Math.max(0, Math.min(100, (current / Math.max(total, 1)) * 100));
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>{label}</span>
        <span className="font-mono">
          {current} / {total}
        </span>
      </div>
      <div className="progress-track">
        <div className="progress-fill" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
