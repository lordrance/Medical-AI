interface Props {
  current: number;
  total: number;
  label?: string;
}

export function ProgressBar({ current, total, label }: Props) {
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
