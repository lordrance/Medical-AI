"use client";

/**
 * V5: React Error Boundary — catches rendering errors and shows a friendly
 * Chinese-language fallback instead of letting the white screen or broken UI
 * propagate. Must be a class component (React constraint).
 *
 * Usage:
 *   <ErrorBoundary>
 *     <MyApp />
 *   </ErrorBoundary>
 */

import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, RefreshCcw } from "lucide-react";

interface Props {
  children: ReactNode;
  /** Optional custom fallback UI. When omitted, the default Chinese prompt is used. */
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Log to console in dev; in production this could route to a monitoring service.
    console.error("[ErrorBoundary]", error, info.componentStack);
  }

  private handleRefresh = (): void => {
    window.location.reload();
  };

  render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback !== undefined) {
        return this.props.fallback;
      }

      return (
        <div className="flex min-h-[60vh] items-center justify-center">
          <div className="mx-auto max-w-sm space-y-5 text-center">
            <div className="flex justify-center">
              <AlertTriangle className="h-16 w-16 text-destructive/70" aria-hidden />
            </div>
            <h2 className="text-xl font-semibold text-foreground">
              页面遇到错误
            </h2>
            <p className="text-sm text-muted-foreground">
              抱歉，页面渲染时出现了意外错误。请尝试刷新页面后重试。
            </p>
            <button
              type="button"
              className="btn-primary inline-flex items-center gap-2 px-5 py-2"
              onClick={this.handleRefresh}
            >
              <RefreshCcw className="h-4 w-4" />
              刷新页面
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
