import { LayoutGrid, Plus, Star } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ElementType, type KeyboardEvent, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import type { EmbedView } from "../../embedding/model";
import { LINE_COPY } from "../copy";
import { ago, type PinnedView, type RecentStep } from "./api";
import { useCorners } from "./cornersStore";
import { BUTTON, EDGE, lensTops, SLOT, type LensKind } from "./geometry";
import { ViewThumb } from "./Thumb";
import { useLens, type LensRow } from "./useLens";

export const LIST_WIDTH = 470;

interface Props {
  open: boolean;
  /** undefined while loading */
  views: readonly PinnedView[] | undefined;
  viewsError?: string;
  recent: readonly RecentStep[] | undefined;
  recentError?: string;
  /** the default name offered for "Pin this view" */
  suggest: string;
  onApply: (spec: Record<string, unknown>, id: string) => void;
  onPin: (name: string) => void;
  onRename: (id: string, name: string) => void;
  onRecentOpen: (open: boolean) => void;
  /** a step whose spec this screen cannot restore */
  canApply: (spec: Record<string, unknown>) => boolean;
  /** flag views-panel: the list sits inside the panel (it fills its parent) instead of floating at the corner */
  embedded?: boolean;
  /** Flag graph-intent: the favorite pages, listed under the pinned views; absent or empty: no section. */
  favorites?: readonly { id: string; title: string }[];
  onFavorite?: (id: string) => void;
  /** Flag graph-intent: opens the view gallery, the last entry of the list; absent: no entry. */
  onAllViews?: () => void;
  /** A shared site: the saved views can be opened, but not pinned, renamed or stepped back through. */
  readOnly?: boolean;
  /** Flag ui.embedding-views: built-in views offered (dashed) until pinned; absent or empty: no section. */
  suggested?: readonly { view: EmbedView; name: string; hint: string }[];
  onSuggest?: (view: EmbedView) => void;
}

type Entry =
  | (LensRow & { type: "pin"; view: PinnedView })
  | (LensRow & { type: "add" })
  | (LensRow & { type: "fav"; id: string; title: string })
  | (LensRow & { type: "div" })
  | (LensRow & { type: "stack" })
  | (LensRow & { type: "all" })
  | (LensRow & { type: "step"; step: RecentStep; index: number })
  | (LensRow & { type: "note"; text: string })
  | (LensRow & { type: "label"; text: string })
  | (LensRow & { type: "sug"; view: EmbedView; name: string; hint: string });

/** the two back layers of the Recent stack: tilted behind the front one, almost flat while the steps are open */
const stackLayer = (k: number, open: boolean): string => {
  if (k === 0) return "none";
  const [x, rot] = open ? (k === 2 ? [-2, -2] : [-1, -1]) : k === 2 ? [-4, -6] : [-2, -3];
  return `translate(${x}px, ${x}px) rotate(${rot}deg)`;
};

const RING = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

/** The list's own text, one line: the name, then the small grey meta at the right end. */
function Pill({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cn("flex h-5 w-[190px] flex-none items-center gap-2 overflow-hidden rounded-full bg-card px-[9px] shadow-[var(--shadow)]", className)}>{children}</span>;
}

export function NameInput({ initial, label, onSubmit }: { initial: string; label: string; onSubmit: (v: string) => void }) {
  const end = useCorners((s) => s.endEdit);
  const [v, setV] = useState(initial);
  return (
    <input
      autoFocus
      aria-label={label}
      value={v}
      maxLength={80}
      onChange={(e) => setV(e.target.value)}
      onFocus={(e) => e.currentTarget.select()}
      onBlur={end}
      onKeyDown={(e: KeyboardEvent<HTMLInputElement>) => {
        if (e.key === "Enter") {
          e.preventDefault();
          const name = v.trim();
          if (name) onSubmit(name);
          end();
        }
      }}
      className="min-w-0 flex-1 bg-transparent text-[11.5px] font-medium outline-none placeholder:text-muted-foreground"
    />
  );
}

/**
 * The pinned views: a floating ")" curve of rows, no card and no title. Each row is a small picture and a one-line
 * pill at half size; under the pointer the Dock lens grows the row and spreads its neighbours. Order: the pinned
 * views, a "+" card to pin the current view, a faint divider, then "Recent" (a stack that unfolds the last steps).
 */
export function PinList({ open, views, viewsError, recent, recentError, suggest, onApply, onPin, onRename, onRecentOpen, canApply, embedded, favorites, onFavorite, onAllViews, readOnly, suggested, onSuggest }: Props) {
  const edit = useCorners((s) => s.edit);
  const active = useCorners((s) => s.activeView);
  const startEdit = useCorners((s) => s.startEdit);
  const openMenu = useCorners((s) => s.openMenu);
  const [recentOpen, setRecentOpen] = useState(false);
  const lens = useRef<HTMLDivElement>(null);
  const els = useRef(new Map<string, HTMLElement>());

  const entries = useMemo<Entry[]>(() => {
    const out: Entry[] = [];
    const hb = (kind: LensKind) => SLOT[kind];
    if (viewsError) out.push({ type: "note", kind: "row", hb: hb("row"), key: "note-views", text: "Pinned views are not available here" });
    for (const v of views ?? []) out.push({ type: "pin", kind: "row", hb: hb("row"), key: `pin-${v.id}`, view: v });
    if (!readOnly) out.push({ type: "add", kind: "add", hb: hb("add"), key: "add" });
    for (const f of favorites ?? []) out.push({ type: "fav", kind: "row", hb: hb("row"), key: `fav-${f.id}`, id: f.id, title: f.title });
    if (suggested?.length && !readOnly) {
      out.push({ type: "label", kind: "row", hb: hb("row"), key: "sug-label", text: "Suggested from meaning" });
      for (const sg of suggested) out.push({ type: "sug", kind: "row", hb: hb("row"), key: `sug-${sg.view}`, ...sg });
    }
    out.push({ type: "div", kind: "div", hb: hb("div"), key: "div" });
    if (!readOnly) out.push({ type: "stack", kind: "stack", hb: hb("stack"), key: "stack" });
    if (recentOpen && !readOnly) {
      if (recentError) out.push({ type: "note", kind: "row", hb: hb("row"), key: "note-recent", text: "Recent steps are not available here" });
      else if (recent && !recent.length) out.push({ type: "note", kind: "row", hb: hb("row"), key: "note-empty", text: "No steps yet" });
      (recent ?? []).forEach((step, index) => out.push({ type: "step", kind: "row", hb: hb("row"), key: `step-${index}-${step.at}`, step, index }));
    }
    if (onAllViews) out.push({ type: "all", kind: "row", hb: hb("row"), key: "all" });
    return out;
  }, [views, viewsError, recent, recentError, recentOpen, favorites, onAllViews, readOnly, suggested]);

  const { focusRow, release, kick } = useLens(lens, entries, els);
  useEffect(() => {
    if (open) kick();
    else release();
  }, [open, kick, release]);

  const tops = useMemo(() => lensTops(entries), [entries]);
  const total = entries.reduce((s, e) => s + e.hb, 0);

  const reg = (key: string) => (el: HTMLElement | null) => {
    if (el) els.current.set(key, el);
    else els.current.delete(key);
  };
  const base = (e: Entry, i: number) => ({
    ref: reg(e.key),
    "data-lens-row": e.type,
    style: { top: tops[i], height: e.hb },
    onFocus: () => focusRow(e.key),
    onBlur: () => release(),
    className: cn("group absolute left-0 flex w-fit items-center gap-2 pl-[22px] text-left [transform-origin:22px_50%] will-change-transform", RING, "rounded-xl"),
  });

  return (
    <div
      role="group"
      aria-label="Pinned views"
      aria-hidden={!open}
      inert={!open}
      data-corners="pins"
      className={cn("pointer-events-none absolute transition-[opacity,transform] duration-300 motion-reduce:transition-none", embedded ? "inset-0" : "z-[16]", !embedded && !open && "-translate-x-1.5 -translate-y-2.5", open ? "translate-y-0 opacity-100" : "opacity-0")}
      style={embedded ? undefined : { left: EDGE, top: EDGE + BUTTON + 4, bottom: 78, width: LIST_WIDTH }}
    >
      <div
        ref={lens}
        className="pointer-events-none absolute inset-0 overflow-y-auto overflow-x-hidden [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        style={{ maskImage: "linear-gradient(transparent 0, black 16px, black calc(100% - 40px), transparent 100%)", WebkitMaskImage: "linear-gradient(transparent 0, black 16px, black calc(100% - 40px), transparent 100%)" }}
      >
        <div className="relative" style={{ height: total + 40 }}>
          {entries.map((e, i) => {
            const b = base(e, i);
            if (e.type === "div")
              return (
                <div key={e.key} ref={b.ref} data-lens-row="div" aria-hidden className={cn("absolute left-0 flex items-center pl-[22px] [transform-origin:22px_50%]")} style={b.style}>
                  <i className="ml-5 block h-px w-10 rounded-sm bg-muted-foreground/70 opacity-70" />
                </div>
              );
            if (e.type === "note")
              return (
                <div key={e.key} ref={b.ref} data-lens-row="note" style={b.style} className={cn(b.className, "pointer-events-auto")}>
                  <span className="h-5 w-[30px] flex-none" />
                  <Pill className="text-[11px] text-muted-foreground">
                    <span className="truncate">{e.text}</span>
                  </Pill>
                </div>
              );
            if (e.type === "label")
              return (
                <div key={e.key} ref={b.ref} data-lens-row="label" aria-hidden style={b.style} className="absolute left-0 flex items-center pl-[60px] [transform-origin:22px_50%]">
                  <span className="text-[10.5px] text-muted-foreground">{e.text}</span>
                </div>
              );
            if (e.type === "sug")
              return (
                <button key={e.key} type="button" {...b} aria-label={`Suggested view: ${e.name}`} title={e.hint} onClick={() => onSuggest?.(e.view)} className={cn(b.className, "pointer-events-auto")}>
                  <span className="block h-5 w-[30px] flex-none rounded-[5px] border border-dashed border-muted-foreground/50" aria-hidden />
                  <Pill className="border border-dashed border-muted-foreground/50 bg-transparent text-muted-foreground shadow-none group-hover:text-foreground">
                    <span className="truncate text-[11.5px]">{e.name}</span>
                  </Pill>
                </button>
              );
            if (e.type === "add") {
              const editing = edit?.kind === "pin";
              const empty = !views?.length;
              const name = <span className="truncate">Pin this view</span>;
              // while the name is typed the row is a plain box: a text field may not sit inside a button
              const Row: ElementType = editing ? "div" : "button";
              return (
                <Row
                  key={e.key}
                  {...(editing ? { role: "group", "aria-label": "Pin this view" } : { type: "button", "aria-label": "Pin this view", title: "Pin this view", onClick: () => startEdit({ kind: "pin" }) })}
                  {...b}
                  className={cn(b.className, "pointer-events-auto")}
                >
                  <span className="grid h-5 w-[30px] flex-none place-items-center rounded-[5px] bg-card text-muted-foreground shadow-[var(--shadow)] group-hover:text-primary">
                    <Plus className="size-[11px]" strokeWidth={1.8} aria-hidden />
                  </span>
                  <Pill className={cn("transition-opacity", editing || empty ? "opacity-100" : "opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100 group-data-[focus=true]:opacity-100")}>
                    {editing ? <NameInput initial={suggest} label="Name for the pinned view" onSubmit={onPin} /> : <span className="text-[11.5px] font-medium">{name}</span>}
                  </Pill>
                </Row>
              );
            }
            if (e.type === "stack")
              return (
                <button
                  key={e.key}
                  type="button"
                  {...b}
                  aria-expanded={recentOpen}
                  aria-label={recentOpen ? "Hide recent steps" : "Show recent steps"}
                  title={recentOpen ? "Hide recent steps" : "Show your recent steps"}
                  onClick={() => {
                    setRecentOpen(!recentOpen);
                    onRecentOpen(!recentOpen);
                  }}
                  className={cn(b.className, "pointer-events-auto")}
                >
                  <span className="relative block h-5 w-[30px] flex-none" aria-hidden>
                    {/* the last steps as a stack of small graphs; it fans out a little on hover and settles when open */}
                    {[2, 1, 0].map((k) => (
                      <span
                        key={k}
                        className="absolute left-0 top-0 block h-5 w-[30px] overflow-hidden rounded-[5px] shadow-[var(--shadow)] transition-transform duration-300 motion-reduce:transition-none"
                        style={{ transform: stackLayer(k, recentOpen), opacity: k === 2 ? 0.7 : k === 1 ? 0.85 : 1 }}
                      >
                        <ViewThumb id={`stack-${k}`} className="block size-full" />
                      </span>
                    ))}
                  </span>
                  <Pill>
                    <span className="text-[11.5px] font-medium">Recent</span>
                    <small className="ml-auto truncate text-[9.5px] text-muted-foreground">{recentOpen ? "hide" : "show"} your last steps</small>
                  </Pill>
                </button>
              );
            if (e.type === "all")
              return (
                <button key={e.key} type="button" {...b} aria-label={LINE_COPY.views.allViews} title={LINE_COPY.views.allViews} onClick={onAllViews} className={cn(b.className, "pointer-events-auto")}>
                  <span className="grid h-5 w-[30px] flex-none place-items-center rounded-[5px] bg-card text-muted-foreground shadow-[var(--shadow)] group-hover:text-primary">
                    <LayoutGrid className="size-[11px]" strokeWidth={1.8} aria-hidden />
                  </span>
                  <Pill>
                    <span className="truncate text-[11.5px] font-medium">{LINE_COPY.views.allViews}</span>
                  </Pill>
                </button>
              );
            if (e.type === "fav")
              return (
                <button key={e.key} type="button" {...b} aria-label={`${LINE_COPY.favorites.heading}: ${e.title}`} title={e.title} onClick={() => onFavorite?.(e.id)} className={cn(b.className, "pointer-events-auto")}>
                  <span className="grid h-5 w-[30px] flex-none place-items-center rounded-[5px] bg-card text-muted-foreground shadow-[var(--shadow)] group-hover:text-primary">
                    <Star className="size-[11px]" strokeWidth={1.8} aria-hidden />
                  </span>
                  <Pill>
                    <span className="truncate text-[11.5px] font-medium">{e.title}</span>
                  </Pill>
                </button>
              );
            const isPin = e.type === "pin";
            const spec = isPin ? e.view.spec : e.step.spec;
            const name = isPin ? e.view.name : e.step.text;
            const meta = isPin ? ago(e.view.created) : ago(e.step.at);
            const ok = canApply(spec);
            const renaming = isPin && edit?.kind === "rename" && edit.id === e.view.id;
            const on = isPin && active === e.view.id;
            const Item: ElementType = renaming ? "div" : "button";
            return (
              <Item
                key={e.key}
                {...(renaming ? { role: "group" } : { type: "button", "aria-pressed": isPin ? on : undefined })}
                {...b}
                aria-label={`${name}${meta ? `, ${meta}` : ""}`}
                aria-disabled={!ok || undefined}
                title={ok ? name : `${name} (this step cannot be restored here)`}
                onClick={() => ok && !renaming && onApply(spec, isPin ? e.view.id : "")}
                onContextMenu={(ev) => {
                  if (!isPin) return;
                  ev.preventDefault();
                  openMenu("pins", e.view.id);
                }}
                className={cn(b.className, "pointer-events-auto", !ok && "opacity-60")}
              >
                <span className={cn("block h-5 w-[30px] flex-none overflow-hidden rounded-[5px] shadow-[var(--shadow)]", on && "ring-2 ring-primary")}>
                  <ViewThumb id={isPin ? e.view.id : `${e.step.at}${e.step.text}`} className="block size-full" />
                </span>
                <Pill>
                  {renaming ? (
                    <NameInput initial={name} label="New name for the pinned view" onSubmit={(v) => onRename(e.view.id, v)} />
                  ) : (
                    <>
                      <span className={cn("max-w-[120px] flex-none truncate text-[11.5px] font-medium", on && "text-primary")}>{name}</span>
                      <small className="ml-auto min-w-0 truncate text-[9.5px] text-muted-foreground">{meta}</small>
                    </>
                  )}
                </Pill>
              </Item>
            );
          })}
        </div>
      </div>
    </div>
  );
}
