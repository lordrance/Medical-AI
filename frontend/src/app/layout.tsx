import type { Metadata } from "next";
import "@/styles/globals.css";
import { zh } from "@/lib/i18n/zh-CN";

export const metadata: Metadata = {
  title: zh.app.title,
  description: zh.app.subtitle,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-Hans">
      <body className="min-h-screen bg-background text-foreground">
        <div className="container max-w-3xl py-8">
          <header className="mb-8 flex items-center justify-between">
            <div>
              <div className="flex items-center gap-2">
                <span
                  aria-hidden
                  className="inline-block h-6 w-1.5 rounded-full bg-primary"
                />
                <h1 className="text-lg font-semibold tracking-tight">
                  {zh.app.title}
                </h1>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                {zh.app.subtitle}
              </p>
            </div>
          </header>
          <main className="animate-fade-in">{children}</main>
          <footer className="mt-16 border-t border-border pt-4 text-xs text-muted-foreground space-y-1">
            <p>{zh.app.footer}</p>
            <p><a href="https://beian.miit.gov.cn/" target="_blank" rel="noopener noreferrer">闽ICP备2026029270号</a></p>
          </footer>
        </div>
      </body>
    </html>
  );
}
