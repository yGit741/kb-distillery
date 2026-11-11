import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { Flag } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react";
import { useDataSource } from "@/api";
import type { PageFlag, PageFlagFixReply } from "@/api/types";
import { Button } from "@/components/ui/button";
import { useVariant, VARIANTS } from "@/components/variants";
import { useApiQuery } from "@/lib/useApiQuery";
import { BLOCKS, blocksOf, type SelectionChip } from "./PageChat";

const norm = (s: string) => s.replace(/\s+/g, " ").trim();

/** The article text with white space collapsed, and for each character the text node and offset it came from. */
function mapped(el: Element): { s: string; pts: { node: Text; off: number }[] } {
  const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  let s = "";
  const pts: { node: Text; off: number }[] = [];
  let prevBlock: Element | null = null;
  let lastSpace = true;
  for (let n = w.nextNode() as Text | null; n; n = w.nextNode() as Text | null) {
    const blk = n.parentElement?.closest(BLOCKS) ?? null;
    if (prevBlock && blk !== prevBlock && !lastSpace) {
      s += " ";
      pts.push({ node: n, off: 0 });
      lastSpace = true;
    }
    prevBlock = blk;
    for (let i = 0; i < n.data.length; i++) {
      if (/\s/.test(n.data[i]!)) {
        if (lastSpace) continue;
        s += " ";
        lastSpace = true;
      } else {
        s += n.data[i];
        lastSpace = false;
      }
      pts.push({ node: n, off: i });
    }
  }
  return { s, pts };
}

/** The Range that covers a flagged span on the rendered page: in its own block first, anywhere on the page otherwise. */
export function findRange(root: HTMLElement, text: string, blockAt: number | null): Range | null {
  const want = norm(text);
  if (!want) return null;
  const blocks = blocksOf(root);
  const own = blockAt !== null ? blocks[blockAt] : undefined;
  for (const el of own ? [own, root] : [root]) {
    const { s, pts } = mapped(el);
    const i = s.indexOf(want);
    if (i < 0) continue;
    const a = pts[i]!;
    const b = pts[i + want.length - 1]!;
    const range = document.createRange();
    range.setStart(a.node, a.off);
    range.setEnd(b.node, b.off + 1);
    return range;
  }
  return null;
}

type Rect = { left: number; top: number; width: number; height: number };
type Placed = { flag: PageFlag; rects: Rect[]; blockTop: number };

/** Where each flag's words are, relative to the article (which is `relative`); flags whose words are gone are left out. */
function place(root: HTMLElement, flags: PageFlag[]): Placed[] {
  const base = root.getBoundingClientRect();
  const out: Placed[] = [];
  const slots = new Map<number, number>();
  for (const flag of flags) {
    const range = findRange(root, flag.text, flag.block_at ?? null);
    if (!range) continue;
    const raw = Array.from(range.getClientRects?.() ?? []);
    const rects = (raw.length ? raw : [{ left: base.left, top: base.top, width: 0, height: 0 }]).map((r) => ({
      left: r.left - base.left,
      top: r.top - base.top,
      width: r.width,
      height: r.height,
    }));
    const blk = (range.startContainer.nodeType === Node.ELEMENT_NODE ? (range.startContainer as Element) : range.startContainer.parentElement)?.closest(BLOCKS);
    const blockTop = blk ? blk.getBoundingClientRect().top - base.top : rects[0]!.top;
    // several flags in one block stack their margin markers instead of sitting on each other
    const slot = slots.get(blockTop) ?? 0;
    slots.set(blockTop, slot + 1);
    out.push({ flag, rects, blockTop: blockTop + slot * 20 });
  }
  return out;
}

/** Flags of one page (the open ones), the mutations, and the last "Fix all flagged" result. */
export function usePageFlags(slug: string, enabled: boolean) {
  const ds = useDataSource();
  const qc = useQueryClient();
  const key = ["pages", "flags", slug];
  const list = useApiQuery(key, (d) => d.listPageFlags(slug), { enabled, retry: false, staleTime: 30_000 });
  const [last, setLast] = useState<PageFlagFixReply | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setLast(null);
    setError(null);
  }, [slug]);
  const refresh = () => qc.invalidateQueries({ queryKey: key });
  const add = useMutation({
    mutationFn: (v: { chip: SelectionChip; note: string }) => ds.addPageFlag(slug, { text: v.chip.text, note: v.note, block_at: v.chip.block_at }),
    onSuccess: refresh,
  });
  const remove = useMutation({ mutationFn: (id: string) => ds.deletePageFlag(slug, id), onSuccess: refresh });
  const fix = useMutation({
    mutationFn: () => ds.fixPageFlags(slug),
    onMutate: () => (setError(null), setLast(null)),
    onSuccess: (r) => {
      setLast(r);
      void refresh();
      void qc.invalidateQueries({ queryKey: ["proposals"] });
    },
    onError: (e) => setError(e instanceof Error ? e.message : String(e)),
  });
  const open = (list.data?.flags ?? []).filter((f) => f.resolved_by === null);
  return {
    enabled,
    open,
    orphaned: open.filter((f) => f.orphaned).length,
    last,
    error,
    markInaccurate: (chip: SelectionChip, note: string) => add.mutate({ chip, note }),
    remove: (id: string) => remove.mutate(id),
    fix: () => fix.mutate(),
    fixing: fix.isPending,
  };
}
export type PageFlagsState = ReturnType<typeof usePageFlags>;

/** The header piece: "n flagged" and the one button that turns every open flag into a single proposal. */
export function FlagsHeader({ flags }: { flags: PageFlagsState }) {
  const n = flags.open.length;
  const reason = flags.fixing ? "A fix is already being prepared." : n === 0 ? "Nothing is flagged yet. Select a sentence and choose Mark inaccurate." : flags.open.every((f) => f.orphaned) ? "Every flagged passage has been rewritten since." : "";
  return (
    <span className="flex flex-wrap items-center gap-2" data-testid="flags-header">
      <span className="rounded-full border px-2 py-0.5 text-xs text-muted-foreground" title={flags.orphaned ? `${flags.orphaned} no longer on the page` : undefined}>
        {n} flagged
      </span>
      <span title={reason || undefined}>
        <Button variant="outline" size="sm" disabled={!!reason} aria-describedby={reason ? "flags-fix-reason" : undefined} onClick={flags.fix}>
          Fix all flagged
        </Button>
      </span>
      {reason && (
        <span id="flags-fix-reason" className="sr-only">
          {reason}
        </span>
      )}
      {flags.fixing && <span className="text-xs text-muted-foreground">Preparing one proposal for {n} flag{n === 1 ? "" : "s"}…</span>}
      {flags.last?.proposal_id && (
        <Link to={`/proposals/${encodeURIComponent(flags.last.proposal_id)}` as "/"} className="text-xs text-primary hover:underline" data-testid="flags-proposal-link">
          Review the proposal ({flags.last.hunks} hunk{flags.last.hunks === 1 ? "" : "s"})
        </Link>
      )}
      {flags.last && !flags.last.proposal_id && <span className="text-xs text-muted-foreground">{flags.last.reply}</span>}
      {flags.error && (
        <span role="alert" className="text-xs text-muted-foreground">
          That did not go through: {flags.error}
        </span>
      )}
    </span>
  );
}

const inside = (r: Rect, x: number, y: number) => x >= r.left - 2 && x <= r.left + r.width + 2 && y >= r.top - 2 && y <= r.top + r.height + 2;

/** The flagged spans drawn over the article in one of three looks; the words themselves are never touched. */
export function FlagMarks({ flags, articleRef, markdown }: { flags: PageFlagsState; articleRef: RefObject<HTMLElement | null>; markdown: string }) {
  const spec = VARIANTS["page-flag-mark"]!;
  const [look] = useVariant("page-flag-mark", spec.options.map((o) => o.id), spec.default);
  const [placed, setPlaced] = useState<Placed[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [pinned, setPinned] = useState<string | null>(null);
  const closer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const key = flags.open.map((f) => f.id + f.text).join("|");

  const measure = useCallback(() => {
    const root = articleRef.current;
    if (root) setPlaced(place(root, flags.open));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [articleRef, key]);
  useLayoutEffect(measure, [measure, markdown]);
  useEffect(() => {
    const root = articleRef.current;
    window.addEventListener("resize", measure);
    const ro = typeof ResizeObserver === "undefined" || !root ? null : new ResizeObserver(measure);
    if (root) ro?.observe(root);
    return () => {
      window.removeEventListener("resize", measure);
      ro?.disconnect();
    };
  }, [articleRef, measure]);

  const hold = () => clearTimeout(closer.current);
  const release = () => {
    hold();
    closer.current = setTimeout(() => setActive(null), 250);
  };
  // A selection in the article always belongs to the selection toolbar: the note never opens over it.
  const selecting = useCallback(() => {
    const root = articleRef.current;
    const sel = window.getSelection();
    return !!root && !!sel && sel.rangeCount > 0 && !!sel.toString().trim() && root.contains(sel.anchorNode);
  }, [articleRef]);
  useEffect(() => {
    const onSelect = () => {
      if (!selecting()) return;
      hold();
      setActive(null);
      setPinned(null);
    };
    document.addEventListener("selectionchange", onSelect);
    document.addEventListener("mouseup", onSelect);
    return () => {
      document.removeEventListener("selectionchange", onSelect);
      document.removeEventListener("mouseup", onSelect);
    };
  }, [selecting]);
  // underline and tint are hit-tested on the article so the words stay selectable and links stay clickable:
  // hover shows the note, a plain click (no selection) pins it, a drag or an existing selection never opens it
  useEffect(() => {
    const root = articleRef.current;
    if (!root || look === "margin") return;
    const hitAt = (e: MouseEvent) => {
      const base = root.getBoundingClientRect();
      return placed.find((p) => p.rects.some((r) => inside(r, e.clientX - base.left, e.clientY - base.top)));
    };
    const onMove = (e: MouseEvent) => {
      if (e.buttons !== 0 || selecting()) return;
      const hit = hitAt(e);
      if (hit) {
        hold();
        setActive(hit.flag.id);
      } else if (active) release();
    };
    const onClick = (e: MouseEvent) => {
      if (selecting() || (e.target as Element | null)?.closest?.("a, button")) return;
      const hit = hitAt(e);
      if (hit) setPinned((p) => (p === hit.flag.id ? null : hit.flag.id));
    };
    root.addEventListener("mousemove", onMove);
    root.addEventListener("click", onClick);
    root.addEventListener("mouseleave", release);
    return () => {
      root.removeEventListener("mousemove", onMove);
      root.removeEventListener("click", onClick);
      root.removeEventListener("mouseleave", release);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [articleRef, look, placed, active, selecting]);

  const shown = pinned ?? active;
  const target = placed.find((p) => p.flag.id === shown);
  return (
    <div className="pointer-events-none absolute inset-0 z-10" data-testid="flag-marks" data-look={look}>
      {placed.map(({ flag, rects, blockTop }) =>
        look === "margin" ? (
          <button
            key={flag.id}
            type="button"
            data-testid="flag-mark"
            aria-label={`Flag: ${flag.note || flag.text}`}
            onMouseEnter={() => (hold(), setActive(flag.id))}
            onMouseLeave={release}
            onClick={() => setPinned((p) => (p === flag.id ? null : flag.id))}
            className="pointer-events-auto absolute -left-6 rounded p-0.5 text-warn hover:bg-muted"
            style={{ top: blockTop + 2 }}
          >
            <Flag className="size-3.5" aria-hidden />
          </button>
        ) : (
          rects.map((r, i) => (
            <span
              key={`${flag.id}-${i}`}
              data-testid="flag-mark"
              data-flag={flag.id}
              aria-hidden
              className={look === "tint" ? "absolute rounded-sm bg-warn/25" : "flag-wave absolute"}
              style={look === "tint" ? { left: r.left, top: r.top, width: r.width, height: r.height } : { left: r.left, top: r.top + r.height - 3, width: r.width }}
            />
          ))
        ),
      )}
      {target && (
        <div
          role="dialog"
          aria-label="Flag"
          onMouseEnter={hold}
          onMouseLeave={release}
          className="pointer-events-auto absolute z-20 w-64 rounded-md border bg-card p-3 text-sm shadow-md"
          style={look === "margin" ? { left: 0, top: target.blockTop + 24 } : { left: Math.max(0, target.rects[0]!.left), top: target.rects[0]!.top + target.rects[0]!.height + 6 }}
        >
          <p className="line-clamp-2 border-l-2 border-warn pl-2 text-xs text-muted-foreground">“{target.flag.text}”</p>
          <p className="mt-2">{target.flag.note || <span className="text-muted-foreground">No note.</span>}</p>
          <div className="mt-2 flex justify-end">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                flags.remove(target.flag.id);
                setActive(null);
                setPinned(null);
              }}
            >
              Remove
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
