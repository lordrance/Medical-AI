import Link from "next/link";
import { Stethoscope, ShieldCheck, Clock } from "lucide-react";
import { zh } from "@/lib/i18n/zh-CN";

export default function HomePage() {
  return (
    <div className="space-y-6 animate-slide-up">
      <section className="card card-section">
        <div className="flex items-start gap-3">
          <div className="rounded-md bg-primary/10 p-2 text-primary">
            <Stethoscope className="h-6 w-6" />
          </div>
          <div className="flex-1">
            <h2 className="text-2xl font-semibold tracking-tight">
              {zh.home.welcome}
            </h2>
            <p className="mt-3 leading-relaxed text-muted-foreground">
              {zh.home.intro}
            </p>
          </div>
        </div>
        <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Pill icon={<ShieldCheck className="h-4 w-4" />}>
            数据脱敏存储 · 仅用于学术研究
          </Pill>
          <Pill icon={<Clock className="h-4 w-4" />}>预计耗时 28–32 分钟</Pill>
        </div>
        <div className="mt-7 rounded-md border border-accent/40 bg-accent/5 p-4 text-sm text-foreground/80">
          {zh.home.notMedical}
        </div>
        <div className="mt-7 flex justify-end">
          <Link href="/consent" className="btn-primary">
            {zh.home.start}
          </Link>
        </div>
      </section>
    </div>
  );
}

function Pill({ icon, children }: { icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2 rounded-md border border-border bg-muted/40 px-3 py-2 text-sm text-foreground/80">
      <span className="text-primary">{icon}</span>
      {children}
    </div>
  );
}
