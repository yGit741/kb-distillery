import { useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { useKb } from "@/lib/store";
import { cn } from "@/lib/utils";
import { describe, type Layer, type ViewStack } from "../layers/model";
import { resolveName } from "../layers/names";
import {
  anchorLayers,
  applyLayers,
  isAnchored,
  specLayers,
  type ReadyCard,
} from "../layers/readyViews";
import { useCapabilities } from "../shell/capabilities";
import { LINE_COPY } from "../shell/copy";
import {
  defaultFetch,
  pinView,
  type PinnedView,
  type RecentStep,
} from "../shell/corners/api";
import { useCorners } from "../shell/corners/cornersStore";
import { ViewThumb } from "../shell/corners/Thumb";
import { useShellStore } from "../shell/shellStore";
import type { GNode } from "../types";
import { useGallery } from "./galleryStore";

const G = LINE_COPY.gallery;
const RECENT_SHOWN = 10;

type Op = "apply" | "add" | "pin";
type Section = "ready" | "pinned" | "recent";

interface Card {
  key: string;
  section: Section;
  name: string;
  description: string;
  /** null: this app cannot run the view (an unreadable line, or a pin from before layer stacks) */
  layers: Layer[] | null;
  legacy?: PinnedView;
  anchored: boolean;
}

interface Props {
  nodes: readonly GNode[];
  ready: readonly ReadyCard[];
  pinned: readonly PinnedView[];
  /** the server's order: oldest first */
  recent: readonly RecentStep[];
  /** after a view was applied or added: the screen keeps it as a recent step */
  onRecord: (name: string, layers: readonly Layer[]) => void;
  /** a pin from before layer stacks opens through the screen's older path */
  onLegacy: (v: PinnedView) => void;
}

const words = (layers: readonly Layer[]) => layers.map(describe).join(" · ");

function buildCards(
  ready: Props["ready"],
  pinned: Props["pinned"],
  recent: Props["recent"],
): Card[] {
  const out: Card[] = ready.map((r) => ({
    key: `ready:${r.id}`,
    section: "ready",
    name: r.name,
    description: r.layers ? r.description : G.cannotRun,
    layers: r.layers,
    anchored: !!r.layers && isAnchored(r.layers),
  }));
  for (const v of pinned) {
    const layers = specLayers(v.spec);
    out.push({
      key: `pinned:${v.id}`,
      section: "pinned",
      name: v.name,
      description: layers ? words(layers) : G.cannotRun,
      layers,
      legacy: layers ? undefined : v,
      anchored: !!layers && isAnchored(layers),
    });
  }
  const seen = new Set<string>();
  for (const s of [...recent].reverse()) {
    if (out.filter((c) => c.section === "recent").length >= RECENT_SHOWN) break;
    const layers = specLayers({
      v: 2,
      layers: (s.spec.stack as ViewStack | undefined)?.layers,
    });
    if (!layers || seen.has(s.text)) continue;
    seen.add(s.text);
    out.push({
      key: `recent:${s.at}:${s.text}`,
      section: "recent",
      name: s.text,
      description: words(layers),
      layers,
      anchored: isAnchored(layers),
    });
  }
  return out;
}

/**
 * The view gallery (flag graph-intent): a window over the graph with every ready, pinned and recent view as a card of
 * a fixed size. Each card applies (replace), adds (stack) or pins. A view that needs one page ("Neighborhood of...")
 * takes the page in focus when exactly one is, and otherwise asks for a name on its own card.
 */
export function Gallery(props: Props) {
  const open = useGallery((s) => s.open);
  const hide = useGallery((s) => s.hide);
  return (
    <Dialog open={open} onOpenChange={(o) => !o && hide()}>
      {open && <GalleryBody {...props} />}
    </Dialog>
  );
}

function GalleryBody({
  nodes,
  ready,
  pinned,
  recent,
  onRecord,
  onLegacy,
}: Props) {
  const hide = useGallery((s) => s.hide);
  const caps = useCapabilities();
  const qc = useQueryClient();
  const selection = useKb((s) => s.selection);
  const [filter, setFilter] = useState("");
  const [typed, setTyped] = useState<Record<string, string>>({});
  const [asking, setAsking] = useState<
    Record<
      string,
      { op: Op; name: string; options: { slug: string; title: string }[] }
    >
  >({});
  const [missing, setMissing] = useState<Record<string, string>>({});
  const grid = useRef<HTMLDivElement>(null);
  const say = (t: string) => useShellStore.getState().say(t);
  // the window replaces the corner lists: they fold away when it opens
  useEffect(() => {
    useCorners.getState().closeAll();
  }, []);

  const byId = useMemo(
    () => new Map(nodes.map((n) => [n.id, n] as const)),
    [nodes],
  );
  const focusSlug = selection.size === 1 ? ([...selection][0] ?? null) : null;
  const focusTitle = focusSlug ? byId.get(focusSlug)?.title || focusSlug : "";

  const cards = useMemo(
    () => buildCards(ready, pinned, recent),
    [ready, pinned, recent],
  );
  const shown = useMemo(() => {
    const ws = filter.toLowerCase().split(/\s+/).filter(Boolean);
    return cards.filter((c) =>
      ws.every(
        (w) =>
          c.name.toLowerCase().includes(w) ||
          c.description.toLowerCase().includes(w),
      ),
    );
  }, [cards, filter]);
  const sections: { id: Section; heading: string }[] = [
    { id: "ready", heading: G.ready },
    { id: "pinned", heading: G.pinned },
    { id: "recent", heading: G.recent },
  ];

  const pinLayers = async (name: string, layers: Layer[]) => {
    try {
      await pinView(defaultFetch, name, { v: 2, layers, text: words(layers) });
      void qc.invalidateQueries({ queryKey: ["views"] });
      void qc.invalidateQueries({ queryKey: ["corners", "views"] });
      say(G.pinned1(name));
    } catch {
      say(G.pinFailed);
    }
  };

  /** Run one action on one card; a view that needs a page and has none asks on its own card. */
  function act(card: Card, op: Op, slug?: string) {
    if (!card.layers) {
      if (card.legacy && op !== "pin") {
        onLegacy(card.legacy);
        hide();
      } else if (!card.legacy) say(LINE_COPY.views.cannotRunSay(card.name));
      return;
    }
    let layers = card.layers;
    let label = card.name;
    if (card.anchored) {
      let page = focusSlug ?? slug;
      if (!page) {
        const name = (typed[card.key] ?? "").trim();
        if (!name) {
          grid.current
            ?.querySelector<HTMLInputElement>(
              `[data-card="${CSS.escape(card.key)}"] input`,
            )
            ?.focus();
          return;
        }
        const r = resolveName(name, nodes);
        if ("slug" in r) page = r.slug;
        else {
          setAsking((a) => ({
            ...a,
            [card.key]: { op, name, options: r.options.slice(0, 3) },
          }));
          setMissing((m) => ({
            ...m,
            [card.key]: r.options.length ? "" : G.noPage(name),
          }));
          return;
        }
      }
      layers = anchorLayers(layers, nodes, page);
      label = `${card.name.replace(/\u2026$/, "").trim()} ${byId.get(page)?.title || page}`;
    }
    setAsking((a) =>
      card.key in a
        ? Object.fromEntries(Object.entries(a).filter(([k]) => k !== card.key))
        : a,
    );
    setMissing((m) => ({ ...m, [card.key]: "" }));
    if (op === "pin") return void pinLayers(label, layers);
    if (applyLayers(op === "add" ? "stack" : "replace", layers)) {
      onRecord(label, layers);
      say(
        op === "add"
          ? LINE_COPY.views.added(label)
          : LINE_COPY.views.applied(label),
      );
    }
    hide();
  }

  const cardEls = () => [
    ...(grid.current?.querySelectorAll<HTMLElement>("[data-card]") ?? []),
  ];
  const onCardKey = (e: KeyboardEvent<HTMLElement>, card: Card) => {
    if (e.target !== e.currentTarget) return;
    const all = cardEls();
    const at = all.indexOf(e.currentTarget);
    const top = all[0]?.getBoundingClientRect().top;
    const cols = Math.max(
      1,
      all.filter((c) => c.getBoundingClientRect().top === top).length,
    );
    const go = (i: number) => {
      e.preventDefault();
      all[Math.max(0, Math.min(all.length - 1, i))]?.focus();
    };
    if (e.key === "ArrowRight") go(at + 1);
    else if (e.key === "ArrowLeft") go(at - 1);
    else if (e.key === "ArrowDown") go(at + cols);
    else if (e.key === "ArrowUp") go(at - cols);
    else if (e.key === "Enter") {
      e.preventDefault();
      act(card, e.shiftKey ? "add" : "apply");
    }
  };

  return (
    <DialogContent
      className="top-[7%] flex h-[min(82vh,760px)] w-[calc(100vw-3rem)] max-w-4xl flex-col"
      aria-describedby="gallery-desc"
    >
      <div className="flex flex-none items-center gap-3 border-b px-4 py-3">
        <DialogTitle className="text-sm font-semibold">{G.title}</DialogTitle>
        <DialogDescription id="gallery-desc" className="sr-only">
          {G.filterPlaceholder}
        </DialogDescription>
        <input
          autoFocus
          aria-label={G.filterLabel}
          placeholder={G.filterPlaceholder}
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              cardEls()[0]?.focus();
            }
          }}
          className="h-8 min-w-0 flex-1 rounded-md border bg-background px-3 text-sm outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring"
        />
        <button
          type="button"
          aria-label={G.close}
          onClick={hide}
          className="grid size-8 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <X className="size-4" strokeWidth={1.6} aria-hidden />
        </button>
      </div>
      <div
        ref={grid}
        className="min-h-0 flex-1 space-y-5 overflow-y-auto px-4 py-4"
      >
        {!shown.length && (
          <p className="text-sm text-muted-foreground">{G.empty}</p>
        )}
        {sections.map((s) => {
          const inSection = shown.filter((c) => c.section === s.id);
          if (!inSection.length) return null;
          return (
            <section key={s.id} aria-label={s.heading}>
              <h3 className="mb-2 text-[10.5px] font-semibold uppercase tracking-[0.06em] text-muted-foreground">
                {s.heading}
              </h3>
              <div className="grid grid-cols-[repeat(auto-fill,minmax(210px,1fr))] gap-3">
                {inSection.map((c) => {
                  const ask = asking[c.key];
                  const dead = !c.layers && !c.legacy;
                  return (
                    <article
                      key={c.key}
                      data-card={c.key}
                      tabIndex={0}
                      aria-label={c.name}
                      onKeyDown={(e) => onCardKey(e, c)}
                      className="flex h-[212px] flex-col gap-1.5 rounded-lg border bg-card p-2.5 text-card-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      <div className="h-[72px] flex-none overflow-hidden rounded-md border">
                        <ViewThumb id={c.key} className="block size-full" />
                      </div>
                      <h4 className="flex-none truncate text-[12.5px] font-medium">
                        {c.name}
                      </h4>
                      <div className="min-h-0 flex-1 overflow-hidden text-[11.5px] leading-snug text-muted-foreground">
                        {ask ? (
                          <div>
                            <p className="mb-1">
                              {ask.options.length
                                ? G.didYouMean
                                : (missing[c.key] ?? "")}
                            </p>
                            <div className="flex flex-wrap gap-1">
                              {ask.options.map((o) => (
                                <button
                                  key={o.slug}
                                  type="button"
                                  onClick={() => act(c, ask.op, o.slug)}
                                  className="max-w-full truncate rounded-md border px-1.5 py-0.5 text-foreground hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                                >
                                  {o.title}
                                </button>
                              ))}
                            </div>
                          </div>
                        ) : (
                          <p className="line-clamp-3">{c.description}</p>
                        )}
                      </div>
                      {c.anchored && (
                        <div className="flex h-7 flex-none items-center">
                          {focusSlug ? (
                            <span className="truncate text-[11.5px] text-muted-foreground">
                              {G.usesFocus(focusTitle)}
                            </span>
                          ) : (
                            <input
                              aria-label={G.nameLabel(c.name)}
                              placeholder={G.namePlaceholder}
                              value={typed[c.key] ?? ""}
                              onChange={(e) => {
                                setTyped((t) => ({
                                  ...t,
                                  [c.key]: e.target.value,
                                }));
                                setAsking((a) =>
                                  Object.fromEntries(
                                    Object.entries(a).filter(
                                      ([k]) => k !== c.key,
                                    ),
                                  ),
                                );
                              }}
                              onKeyDown={(e) => {
                                if (e.key !== "Enter") return;
                                e.preventDefault();
                                act(c, e.shiftKey ? "add" : "apply");
                              }}
                              className="h-7 w-full min-w-0 rounded-md border bg-background px-2 text-[11.5px] outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring"
                            />
                          )}
                        </div>
                      )}
                      <div className="flex h-7 flex-none items-center gap-1">
                        {(["apply", "add", "pin"] as const).map((op) => {
                          if (op === "pin" && (c.section === "pinned" || !caps.saveViews))
                            return null;
                          return (
                            <button
                              key={op}
                              type="button"
                              disabled={dead || (op === "pin" && !c.layers)}
                              onClick={() => act(c, op)}
                              aria-label={`${G[op]} ${c.name}`}
                              className={cn(
                                "h-6 rounded-md px-2 text-[11.5px] text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50",
                                op === "apply" && "text-foreground",
                              )}
                            >
                              {G[op]}
                            </button>
                          );
                        })}
                      </div>
                    </article>
                  );
                })}
              </div>
            </section>
          );
        })}
      </div>
    </DialogContent>
  );
}
