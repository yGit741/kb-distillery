import { lazy, Suspense } from "react";
import { ErrorBoundary } from "@/components/states";
import { useFlag } from "@/flags/useFlag";
import { useSparkPanel } from "./sparkPanelStore";

// loads on first open, and never in a share build (the MODE test is replaced at build time: a snapshot carries no chat code)
const SparkPanel = import.meta.env.MODE === "share" ? null : lazy(() => import("./SparkPanel").then((m) => ({ default: m.SparkPanel })));

/** Whether the left chat panel is on show: flag `spark-chat` and opened from the spark corner. */
export function useSparkOpen(): boolean {
  const on = useFlag("spark-chat");
  const open = useSparkPanel((s) => s.open);
  return on && open && SparkPanel !== null;
}

export function SparkPanelHost({ scope }: { scope?: string }) {
  const show = useSparkOpen();
  const key = useSparkPanel((s) => s.key);
  if (!show || !SparkPanel) return null;
  return (
    <ErrorBoundary label="Chat">
      <Suspense fallback={null}>
        <SparkPanel key={key} scope={scope} />
      </Suspense>
    </ErrorBoundary>
  );
}
