import { Link } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useApiQuery } from "@/lib/useApiQuery";
import { cn } from "@/lib/utils";
import { tiles, type HealthLike, type LifecycleLike, type OpsLike, type Tone } from "./model";

const DOT: Record<Tone, string> = { ok: "bg-ok", warn: "bg-warn", bad: "bg-bad", "": "bg-muted-foreground/40" };

/**
 * One line at the bottom of every screen: the System strip in miniature. Each item opens its System tab.
 * Lint reads the health snapshot only if System already loaded it (it costs a lint run), so the bar never
 * makes a page slow.
 */
export function StatusBar() {
  const lc = useApiQuery(["lifecycle"], (d) => d.getLifecycle(), { staleTime: 60_000 });
  const ops = useApiQuery(["ops"], (d) => d.getOps(), { staleTime: 60_000 });
  const health = useQuery({ queryKey: ["health"], enabled: false });
  const items = tiles(lc.data as LifecycleLike | undefined, ops.data as OpsLike | undefined, health.data as HealthLike | undefined).filter(
    (t) => t.value !== "…",
  );
  if (!items.length) return null;
  return (
    <footer aria-label="Status" className="fixed inset-x-0 bottom-0 z-40 flex h-7 items-center gap-4 overflow-x-auto border-t bg-card px-4 text-xs text-muted-foreground [scrollbar-width:none]">
      {items.map((t) => (
        <Link
          key={t.id}
          to={"/system" as "/"}
          search={(t.tab === "overview" ? {} : { tab: t.tab }) as never}
          title={t.hint}
          className="flex shrink-0 items-center gap-1.5 hover:text-foreground"
        >
          <span aria-hidden className={cn("size-1.5 rounded-full", DOT[t.tone])} />
          <span>{t.label}</span>
          <span className="font-medium text-foreground tabular-nums">{t.value}</span>
        </Link>
      ))}
    </footer>
  );
}
