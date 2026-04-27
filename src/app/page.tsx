import Link from "next/link";

export default function Home() {
  return (
    <div className="space-y-6">
      <div className="card p-8">
        <h2 className="text-2xl font-semibold text-slate-900">Welcome</h2>
        <p className="mt-2 text-slate-700">
          You are about to participate in a scripted research study about
          reviewing AI-drafted patient messages. The full session takes about
          30 minutes.
        </p>
        <p className="mt-2 text-sm text-slate-500">
          This is <strong>not</strong> a live medical service. All cases are
          fictional and frozen for experimental control.
        </p>
        <div className="mt-6">
          <Link href="/consent" className="btn-primary">
            Start
          </Link>
        </div>
      </div>
    </div>
  );
}
