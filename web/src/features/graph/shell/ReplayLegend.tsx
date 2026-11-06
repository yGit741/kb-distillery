/** What the replay's marks mean (flag `spark-chat`), under the graph while a replay is open. */
export function ReplayLegend({ atEnd }: { atEnd: boolean }) {
  const dot = "inline-block size-3 shrink-0 rounded-full border-[1.5px]";
  return (
    <ul aria-label="Replay legend" data-testid="replay-legend" className="pointer-events-none absolute bottom-3 right-3 z-10 flex flex-col gap-1 rounded-xl border bg-card/95 px-3 py-2 text-xs text-muted-foreground shadow-[var(--shadow)]">
      <li className="flex items-center gap-2">
        <span aria-hidden className={`${dot} border-muted-foreground`} /> seen in results
      </li>
      <li className="flex items-center gap-2">
        <span aria-hidden className={`${dot} border-foreground bg-foreground/25`} /> read
      </li>
      <li className="flex items-center gap-2">
        <span aria-hidden className={`${dot} border-primary bg-primary/25`} /> cited in the answer
      </li>
      <li className="flex items-center gap-2">
        <span aria-hidden className="inline-block size-3 shrink-0 rounded-full border-2 border-primary" /> this step
      </li>
      {atEnd && (
        <li className="flex items-center gap-2">
          <span aria-hidden className={`${dot} border-dashed border-foreground`} /> one link away, not read
        </li>
      )}
    </ul>
  );
}
