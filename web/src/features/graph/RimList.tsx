import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowDownWideNarrow, ArrowUpNarrowWide, Search, X } from "lucide-react";
import { useKb } from "@/lib/store";
import { cn } from "@/lib/utils";
import { useTheme } from "@/theme/theme";
import { useRimList } from "./rimListStore";
import { DEPTH_LABEL, RAMP_BY, colorOf, effectiveColorBy, type ColorBy } from "./style";
import type { GNode } from "./types";

type Sort = "digest" | "year" | "title";
const DEPTH_RANK: Record<string, number> = { deep: 0, full: 1, easy: 2, listed: 3 };
const RING = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

/**
 * Citations by meaning (flag citations-meaning): the list of one topic's uncited papers, opened by a click on its
 * clump or its name. The canvas never moves; the list is where the titles are read. A row opens the paper as a
 * node click does; a dot clicked on the canvas scrolls its row into view.
 */
export function RimList({ byId, colorBy }: { byId: ReadonlyMap<string, GNode>; colorBy: ColorBy }) {
  const open = useRimList((s) => s.open);
  const focus = useRimList((s) => s.focus);
  const close = useRimList((s) => s.close);
  const theme = useTheme((s) => s.theme);
  const [sort, setSort] = useState<Sort>("digest");
  // each sort has its natural direction (deepest digest, newest, A to Z); the arrow flips it
  const [flip, setFlip] = useState(false);
  const [q, setQ] = useState("");
  useEffect(() => {
    setQ("");
    setFlip(false);
  }, [open?.name]);
  const list = useRef<HTMLUListElement>(null);
  const by = effectiveColorBy(colorBy);
  const rows = useMemo(() => {
    const ns = (open?.ids ?? []).map((id) => byId.get(id)).filter((n): n is GNode => !!n);
    const title = (n: GNode) => n.title || n.id;
    const words = q.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const hit = (n: GNode) => words.every((w) => `${title(n)} ${n.year ?? ""}`.toLowerCase().includes(w));
    const sorted = ns.filter(hit).sort((a, b) =>
      sort === "year"
        ? (b.year ?? 0) - (a.year ?? 0) || title(a).localeCompare(title(b))
        : sort === "title"
        ? title(a).localeCompare(title(b))
        : (DEPTH_RANK[a.depth || "listed"] ?? 9) - (DEPTH_RANK[b.depth || "listed"] ?? 9) || title(a).localeCompare(title(b)),
    );
    return flip ? sorted.reverse() : sorted;
  }, [open, byId, sort, flip, q]);
  useEffect(() => {
    if (!focus) return;
    list.current?.querySelector(`[data-id="${CSS.escape(focus)}"]`)?.scrollIntoView({ block: "nearest" });
  }, [focus, rows]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, close]);
  if (!open) return null;
  return (
    <aside
      aria-label={`${open.name}: uncited papers`}
      data-testid="rim-list"
      className="pointer-events-auto absolute bottom-16 right-4 top-20 z-[40] flex w-[360px] flex-col overflow-hidden rounded-[14px] border bg-card shadow-[var(--shadow)]"
    >
      <header className="flex items-start gap-2 border-b px-4 pb-2.5 pt-3">
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-sm font-semibold" title={open.name}>
            {open.name}
          </h2>
          <p className="text-xs text-muted-foreground">
            {q.trim() ? `${rows.length} of ${open.ids.length}` : rows.length} uncited {open.ids.length === 1 ? "paper" : "papers"}
          </p>
        </div>
        <label className="flex items-center gap-1 text-xs text-muted-foreground">
          Sort
          <select value={sort} onChange={(e) => setSort(e.target.value as Sort)} aria-label="Sort the papers" className={cn("rounded bg-transparent px-1 py-0.5 text-xs text-foreground hover:bg-accent", RING)}>
            <option value="digest">Digest</option>
            <option value="year">Year</option>
            <option value="title">Title</option>
          </select>
        </label>
        <button
          type="button"
          onClick={() => setFlip((f) => !f)}
          aria-label={flip ? "Sort the other way (now reversed)" : "Reverse the order"}
          aria-pressed={flip}
          title={flip ? "Reversed: press for the natural order" : "Reverse the order"}
          className={cn("grid size-6 place-items-center rounded-full text-muted-foreground hover:bg-accent hover:text-foreground", RING)}
        >
          {flip ? <ArrowUpNarrowWide aria-hidden className="size-3.5" strokeWidth={1.6} /> : <ArrowDownWideNarrow aria-hidden className="size-3.5" strokeWidth={1.6} />}
        </button>
        <button type="button" onClick={close} aria-label="Close the list" title="Close (Esc)" className={cn("grid size-6 place-items-center rounded-full text-muted-foreground hover:bg-accent hover:text-foreground", RING)}>
          <X aria-hidden className="size-3.5" strokeWidth={1.6} />
        </button>
      </header>
      <label className="mx-3 mt-2 flex items-center gap-2 rounded-lg border bg-background px-2.5 py-1.5 text-sm focus-within:ring-2 focus-within:ring-ring">
        <Search aria-hidden className="size-3.5 flex-none text-muted-foreground" strokeWidth={1.6} />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search these papers"
          aria-label="Search these papers"
          className="min-w-0 flex-1 bg-transparent outline-none placeholder:text-muted-foreground"
        />
        {q && (
          <button type="button" onClick={() => setQ("")} aria-label="Clear the search" className={cn("grid size-5 place-items-center rounded-full text-muted-foreground hover:text-foreground", RING)}>
            <X aria-hidden className="size-3" strokeWidth={1.6} />
          </button>
        )}
      </label>
      <ul ref={list} className="min-h-0 flex-1 overflow-y-auto py-1">
        {rows.map((n) => (
          <li key={n.id} data-id={n.id}>
            <button
              type="button"
              onClick={() => {
                useRimList.setState({ focus: n.id });
                useKb.getState().setSelection([n.id]);
              }}
              className={cn("flex min-h-9 w-full items-center gap-2.5 px-4 py-1.5 text-left text-[13px] hover:bg-accent", n.id === focus && "bg-accent", RING)}
            >
              <i aria-hidden className="block size-2.5 flex-none rounded-full" style={{ background: colorOf(n, by, undefined, RAMP_BY.has(by) ? theme : null) }} />
              <span className="line-clamp-2 min-w-0 flex-1" title={`${n.title} (${DEPTH_LABEL[n.depth || "listed"] ?? n.depth})`}>
                {n.title || n.id}
              </span>
              <span className="flex-none tabular-nums text-xs text-muted-foreground">{n.year ?? ""}</span>
            </button>
          </li>
        ))}
      </ul>
    </aside>
  );
}
