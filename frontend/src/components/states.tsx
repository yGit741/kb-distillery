import { Component, type ErrorInfo, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

/** Loading placeholder: `rows` skeleton bars inside a labelled status region. */
export function Loading({ label = "Loading", rows = 3 }: { label?: string; rows?: number }) {
  return (
    <div className="flex flex-col gap-3" role="status" aria-label={label}>
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-16" />
      ))}
    </div>
  );
}

/** Nothing to show (a filter with no match, a list with no rows). */
export const Empty = ({ children }: { children: ReactNode }) => (
  <p className="py-4 text-center text-sm text-foreground/75">{children}</p>
);

/** Error card with a retry button. */
export function ErrorState({ title, error, onRetry }: { title: string; error?: unknown; onRetry?: () => void }) {
  const detail = error instanceof Error ? error.message : error ? String(error) : "";
  return (
    <Card role="alert" className="border-bad">
      <CardContent className="flex flex-col gap-2 p-4">
        <p className="font-medium text-bad">{title}</p>
        {detail && <p className="text-sm text-muted-foreground break-words">{detail}</p>}
        {onRetry && (
          <Button variant="secondary" size="sm" className="self-start" onClick={onRetry}>
            Try again
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

interface BoundaryProps {
  children: ReactNode;
  label?: string;
}

/** Catches a render error in one screen so the shell (nav, palette, theme) keeps working. */
export class ErrorBoundary extends Component<BoundaryProps, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("screen crashed", error, info.componentStack);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <ErrorState
        title={`${this.props.label ?? "This screen"} crashed.`}
        error={error}
        onRetry={() => this.setState({ error: null })}
      />
    );
  }
}
