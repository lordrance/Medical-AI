import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Draft Review Study",
  description: "A scripted research platform for clinician review of AI drafts.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <div className="mx-auto flex min-h-screen w-full max-w-5xl flex-col px-4 py-8">
          <header className="mb-6 flex items-center justify-between">
            <div>
              <h1 className="text-xl font-semibold text-brand-700">
                AI Draft Review Study
              </h1>
              <p className="text-xs text-slate-500">
                Scripted research platform · not a live medical service
              </p>
            </div>
          </header>
          <main className="flex-1">{children}</main>
          <footer className="mt-12 border-t border-slate-200 pt-4 text-xs text-slate-400">
            Internal research use only · v0.1
          </footer>
        </div>
      </body>
    </html>
  );
}
