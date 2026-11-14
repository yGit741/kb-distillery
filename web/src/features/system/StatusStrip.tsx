import { ExternalLink } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { Event, Tile, Tone } from "./model";

// warn text is amber (under 4.5:1 on white): the dot carries the warning, the value stays readable.
export const TONE_TEXT: Record<Tone, string> = { ok: "text-ok", warn: "text-foreground", bad: "text-bad", "": "text-foreground" };
export const TONE_DOT: Record<Tone, string> = { ok: "bg-ok", warn: "bg-warn", bad: "bg-bad", "": "bg-muted-foreground/40" };

/** One row of status tiles; each opens the tab its number comes from. Used by System and (flag ui.data-system-split) Ingest. */
export function StatusStrip({ items, onOpen, label, cols = "lg:grid-cols-5" }: { items: Tile[]; onOpen: (tab: string) => void; label: string; cols?: string }) {
  return (
    <div className={cn("grid grid-cols-2 gap-2 sm:grid-cols-3", cols)} aria-label={label}>
      {items.map((t) => (
        <button
          key={t.id}
          type="button"
          data-testid={`tile-${t.id}`}
          data-tone={t.tone}
          onClick={() => onOpen(t.tab)}
          className="flex min-w-0 flex-col gap-0.5 rounded-xl border bg-card p-3 text-left shadow-[var(--shadow)] hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        >
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <span aria-hidden className={cn("size-2 rounded-full", TONE_DOT[t.tone])} />
            {t.label}
          </span>
          <span data-testid={`tile-${t.id}-value`} className={cn("text-lg font-semibold tabular-nums", TONE_TEXT[t.tone])}>{t.value}</span>
          <span className="truncate text-xs text-muted-foreground" title={t.hint}>
            {t.hint || " "}
          </span>
        </button>
      ))}
    </div>
  );
}

export const fmtTime = (iso: string) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
};

/** A short list of events, newest first: time, a kind badge, the title and its detail line. */
export function EventList({ events, label }: { events: Event[]; label: string }) {
  return (
    <ol className="flex flex-col" aria-label={label}>
      {events.map((e, i) => (
        <li key={`${e.at}-${i}`} className="flex gap-3 border-b py-2 last:border-b-0">
          <span className="w-28 shrink-0 pt-0.5 text-xs text-muted-foreground tabular-nums">{fmtTime(e.at)}</span>
          <div className="min-w-0 flex-1">
            <p className="flex items-start gap-2 text-sm">
              <Badge variant={e.kind === "knowledge" ? "primary" : e.kind === "nightly" ? (e.tone === "bad" ? "bad" : e.tone === "warn" ? "warn" : "ok") : "outline"} className="shrink-0">
                {e.kind}
              </Badge>
              <span className="min-w-0 break-words">{e.title}</span>
            </p>
            {e.sub && (
              <p className="mt-0.5 text-xs text-muted-foreground">
                {e.href ? (
                  <a href={e.href} target="_blank" rel="noreferrer" className="hover:underline">
                    {e.sub} <ExternalLink aria-hidden className="inline size-3" />
                  </a>
                ) : (
                  e.sub
                )}
              </p>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}
