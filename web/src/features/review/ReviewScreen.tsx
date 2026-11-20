import { Link, useSearch } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronDown, Clock, Inbox, Keyboard, Pencil, Undo2, X } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { useDataSource } from "@/api";
import { Button } from "@/components/ui/button";
import { ErrorState, Loading } from "@/components/states";
import { useApiQuery } from "@/lib/useApiQuery";
import { cn } from "@/lib/utils";
import { reviewApi, type Card, type Deck } from "./api";
import { ApplyDialog, type ApplyPhase } from "./ApplyDialog";
import { ChangeCard, CoverCard, StackCard, type Revised } from "./Cards";
import { EditLine, type EditLineHandle } from "./EditLine";
import { addMark, HIGHLIGHT, MAX_MARKS, paintMarks } from "./marks";
import {
  applyPlan, batchOf, buildItems, decide, emptyState, initialDecisions, itemCards, later, loadState, openStack, passCover, plural, prune,
  reviewLater, saveState, undo, type Command, type DeckState, type Item,
} from "./model";
import { Queue, queueRows, type QueueRow } from "./Queue";
import { pagesFromRows, ReachGraph, type Found, type Picked, type ReachGraphHandle } from "./ReachGraph";
import { isSample, SAMPLE_DECK, SAMPLE_JOBS, SAMPLE_REWRITE, sampleSearch } from "./sample";
import { RESET_EVENT } from "./tours";

const KEYS: [string, string][] = [
  ["A  →", "Accept"], ["R  ←", "Reject"], ["S  ↓", "Later"], ["E", "Edit in words"], ["/", "Commands (/merge, /split)"], ["Z", "Undo (until Apply)"],
  ["Space", "Show more"], ["J  K", "Next / previous without deciding"], ["O", "Open a stack"], ["⌘ ↵", "Apply"],
  ["G", "Search the graph"], ["[  ]", "Move between pages in the graph"], ["X", "Pick the page for your edit"], ["M", "Add the selected text to your edit"],
  ["Q", "Queue (narrow screens)"], ["?", "These keys"],
];

const reducedMotion = () => globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
function useMedia(query: string) {
  const get = () => globalThis.matchMedia?.(query).matches ?? true;
  const [on, setOn] = useState(get);
  useEffect(() => {
    const m = globalThis.matchMedia?.(query);
    if (!m) return;
    const fn = () => setOn(m.matches);
    m.addEventListener?.("change", fn);
    return () => m.removeEventListener?.("change", fn);
  }, [query]);
  return on;
}
const typing = (t: EventTarget | null) =>
  t instanceof HTMLElement && (t.isContentEditable || ["TEXTAREA", "SELECT"].includes(t.tagName) || (t instanceof HTMLInputElement && !["checkbox", "radio"].includes(t.type)));

export function ReviewScreen() {
  const sample = isSample(useSearch({ strict: false }) as Record<string, unknown>);
  const api = useMemo(() => reviewApi(), []);
  const ds = useDataSource();
  const wide = useMedia("(min-width: 1280px)");
  const medium = useMedia("(min-width: 1024px)");
  const qc = useQueryClient();
  const kbQ = useApiQuery(["kb"], (ds) => ds.getKb(), { enabled: !sample, staleTime: 60_000 });
  const deckQ = useQuery({ queryKey: ["review-deck"], queryFn: api.deck, enabled: !sample });
  const [sampleDeck, setSampleDeck] = useState<Deck>(SAMPLE_DECK);
  const deck = sample ? sampleDeck : deckQ.data;
  const kbId = sample ? "sample" : (kbQ.data?.id ?? null);
  const readOnly = !sample && !!kbQ.data?.read_only;

  // --- the person's decisions: in this browser until Apply ---------------------------------------------------------
  const [state, setState] = useState<DeckState>(emptyState);
  const loadedFor = useRef<string | null>(null);
  useEffect(() => {
    if (!deck || !kbId) return;
    if (loadedFor.current !== kbId) {
      loadedFor.current = kbId;
      const saved = sample ? emptyState() : loadState(kbId);
      setState(prune({ ...saved, decisions: { ...initialDecisions(deck.cards), ...saved.decisions } }, deck.cards));
    } else setState((s) => prune(s, deck.cards));
  }, [deck, kbId, sample]);
  useEffect(() => {
    if (kbId && !sample && loadedFor.current === kbId) saveState(kbId, state);
  }, [state, kbId, sample]);
  useEffect(() => {
    if (!sample) return;
    const onReset = () => {
      setSampleDeck(SAMPLE_DECK);
      setState(emptyState());
      setOffset(0);
      setRevised(null);
    };
    window.addEventListener(RESET_EVENT, onReset);
    return () => window.removeEventListener(RESET_EVENT, onReset);
  }, [sample]);

  const cards = deck?.cards ?? [];
  const [filter, setFilter] = useState<{ proposalId: string; label: string } | null>(null);
  const shown = useMemo(() => (filter ? cards.filter((c) => c.proposal_id === filter.proposalId) : cards), [cards, filter]);
  const items = useMemo(() => buildItems(shown, state), [shown, state]);
  const [offset, setOffset] = useState(0);
  const [focusId, setFocusId] = useState<string | null>(null);
  useEffect(() => {
    if (!focusId) return;
    const i = items.findIndex((it) => it.id === focusId);
    if (i >= 0) setOffset(i);
    if (i >= 0 || deck) setFocusId(null);
  }, [focusId, items, deck]);
  const at = Math.min(offset, Math.max(items.length - 1, 0));
  const item: Item | undefined = items[at];
  const card: Card | null = item?.kind === "card" ? item.card : null;

  // --- what goes with the next edit: pages picked in the graph, passages marked on the card ----------------------------
  const [picked, setPicked] = useState<Picked[]>([]);
  const [marks, setMarks] = useState<string[]>([]);
  useEffect(() => {
    setPicked([]);
    setMarks([]);
  }, [item?.id]);
  const togglePick = useCallback((p: Picked) => setPicked((s) => (s.some((x) => x.slug === p.slug) ? s.filter((x) => x.slug !== p.slug) : [...s, p])), []);
  const context = useMemo(() => ({ pages: picked, marks }), [picked, marks]);
  const suggested = useMemo(() => (card?.reach?.pages ?? []).filter((p) => p.exists).map(({ slug, title }) => ({ slug, title })), [card]);
  const pagesQ = useApiQuery(["pages-index"], (d) => d.listPages(), { enabled: !sample, staleTime: 60_000 });
  const titles = useMemo(() => new Map((pagesQ.data?.pages ?? []).map((p) => [p.id, p.title] as const)), [pagesQ.data]);
  const graph = useRef<ReachGraphHandle>(null);
  const searchGraph = useCallback(async (text: string): Promise<Found> => {
    const exclude = card?.hunk.slug ?? "";
    if (sample) return sampleSearch(text, exclude);
    const res = await ds.shapeGraph(text);
    return { pages: pagesFromRows(res.rows, titles, exclude), explanation: res.explanation, cypher: res.cypher ?? null };
  }, [card, sample, ds, titles]);

  const decided = Object.keys(state.decisions).length;
  const accepted = Object.values(state.decisions).filter((d) => d === "accept").length;
  const rows = useMemo(() => applyPlan(cards, deck?.proposals ?? [], state), [cards, deck, state]);
  const steps = rows.filter((r) => r.outcome === "apply").length;
  const position = `${Math.min(decided + state.later.length + 1, cards.length)} of ${cards.length}`;

  // --- motion: a card leaves in the direction of the decision, the next one settles in ------------------------------
  const cardEl = useRef<HTMLDivElement>(null);
  const [announce, setAnnounce] = useState("");
  useLayoutEffect(() => {
    const el = cardEl.current;
    if (!el || !item || typeof el.animate !== "function") return;
    el.animate(reducedMotion() ? [{ opacity: 0 }, { opacity: 1 }] : [{ opacity: 0, transform: "scale(0.98)" }, { opacity: 1, transform: "none" }], { duration: 160, easing: "ease-out" });
  }, [item?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const leave = useCallback(async (dir: number) => {
    const el = cardEl.current;
    if (!el || typeof el.animate !== "function") return;
    const from = el.style.transform || "none";
    const to = reducedMotion() || !dir ? "none" : `translateX(${dir * 24}px) rotate(${dir * 2}deg)`;
    await el.animate([{ opacity: 1, transform: from }, { opacity: 0, transform: to }], { duration: 180, easing: "ease-out", fill: "forwards" }).finished.catch(() => undefined);
    el.style.transform = "";
    el.getAnimations().forEach((a) => a.cancel());
  }, []);

  // --- marking: select text on the card, then the pill (or M) adds it to the edit -----------------------------------------
  const [pill, setPill] = useState<{ x: number; y: number; text: string } | null>(null);
  useEffect(() => {
    const onSel = () => {
      const sel = window.getSelection();
      const el = cardEl.current;
      if (!sel || sel.isCollapsed || !sel.rangeCount || !el) return setPill(null);
      const r = sel.getRangeAt(0);
      const host = r.commonAncestorContainer instanceof Element ? r.commonAncestorContainer : r.commonAncestorContainer.parentElement;
      const text = sel.toString().trim();
      if (!text || !el.contains(r.commonAncestorContainer) || host?.closest("input,textarea,[data-no-mark]")) return setPill(null);
      const b = r.getBoundingClientRect();
      setPill({ x: b.left + b.width / 2, y: b.top, text });
    };
    document.addEventListener("selectionchange", onSel);
    return () => document.removeEventListener("selectionchange", onSel);
  }, []);
  const markSelection = useCallback(() => {
    const text = window.getSelection()?.toString() ?? "";
    if (!text.trim() || item?.kind !== "card") return;
    setMarks((m) => addMark(m, text));
    window.getSelection()?.removeAllRanges();
    setPill(null);
  }, [item]);
  useEffect(() => paintMarks(cardEl.current, marks), [marks, item?.id]);

  // --- decisions ----------------------------------------------------------------------------------------------------
  const [expanded, setExpanded] = useState(false);
  const [keysOpen, setKeysOpen] = useState(false);
  const act = useCallback(async (what: "accept" | "reject" | "later" | "open") => {
    if (!item || readOnly) return;
    if (item.kind === "cover") {
      if (what === "reject") return;
      await leave(what === "later" ? 0 : 1);
      setState((s) => (what === "later" ? later(s, item.cards.map((c) => c.id)) : passCover(s, item.group)));
      setAnnounce(what === "later" ? "Source left for later" : "Reviewing the source's cards");
      return;
    }
    if (what === "open") {
      if (item.kind === "stack") setState((s) => openStack(s, item.klass));
      return;
    }
    const ids = itemCards(item).map((c) => c.id);
    await leave(what === "accept" ? 1 : what === "reject" ? -1 : 0);
    setExpanded(false);
    setState((s) => (what === "later" ? later(s, ids) : decide(s, ids, what)));
    const label = item.kind === "card" ? item.card.page_title : plural(ids.length, "change");
    setAnnounce(`${what === "accept" ? "Accepted" : what === "reject" ? "Rejected" : "Later"}: ${label}`);
  }, [item, readOnly, leave]);
  const takeBack = useCallback(() => {
    setState((s) => {
      const { state: next, undone } = undo(s);
      if (undone) setAnnounce("Taken back");
      if (undone && undone.type !== "cover") setFocusId(undone.ids.length > 1 ? null : undone.ids[0]!);
      return next;
    });
  }, []);

  // --- drag (mouse or touch; never the trackpad's two-finger swipe, which is browser Back) ---------------------------
  const drag = useRef<{ x: number; dx: number; on: boolean; id: number } | null>(null);
  const [dx, setDx] = useState(0);
  const onPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (readOnly || item?.kind === "cover" || e.button !== 0 || (e.target as HTMLElement).closest("button,a,input,textarea,[role=listbox],p,pre,li,code,blockquote,td,h1,h2,h3,mark,ins,del")) return;
    drag.current = { x: e.clientX, dx: 0, on: false, id: e.pointerId };
  };
  const onPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    if (!d || d.id !== e.pointerId) return;
    d.dx = e.clientX - d.x;
    if (!d.on && Math.abs(d.dx) > 8 && !window.getSelection()?.toString()) {
      d.on = true;
      e.currentTarget.setPointerCapture(e.pointerId);
    }
    if (d.on && cardEl.current) {
      cardEl.current.style.transform = `translateX(${d.dx}px) rotate(${Math.max(-3, Math.min(3, d.dx / 40))}deg)`;
      setDx(d.dx);
    }
  };
  const onPointerUp = (e: ReactPointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    drag.current = null;
    if (!d?.on) return;
    e.currentTarget.releasePointerCapture?.(e.pointerId);
    const w = cardEl.current?.offsetWidth ?? 600;
    const explicitAccept = d.dx > 0 && item?.kind === "card" && item.card.tier === "explicit";
    setDx(0);
    if (Math.abs(d.dx) > w * 0.35 && !explicitAccept) void act(d.dx > 0 ? "accept" : "reject");
    else {
      if (explicitAccept) setAnnounce("This kind of change is accepted with the button or A, not by dragging");
      cardEl.current?.animate([{ transform: cardEl.current.style.transform }, { transform: "none" }], { duration: 160, easing: "ease-out" });
      if (cardEl.current) cardEl.current.style.transform = "";
    }
  };

  // --- the edit line -------------------------------------------------------------------------------------------------
  const edit = useRef<EditLineHandle>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [editError, setEditError] = useState<string | null>(null);
  const [revised, setRevised] = useState<Revised | null>(null);
  const [vsPrev, setVsPrev] = useState(false);
  const run = useRef(0);
  const refetch = useCallback(async () => {
    await qc.invalidateQueries({ queryKey: ["review-deck"] });
    void qc.invalidateQueries({ queryKey: ["proposals"] });
  }, [qc]);

  const submit = useCallback(async (cmd: Command) => {
    setEditError(null);
    if (cmd.kind === "help") return;
    if (cmd.kind === "unknown") return setEditError(`There is no ${cmd.name}: try /merge @page or /split.`);
    if (!card) return setEditError("Open a single change to edit it (O opens a stack).");
    const mine = ++run.current;
    const slug = card.hunk.slug;
    try {
      if (cmd.kind === "instruction") {
        setBusy("Rewriting…");
        if (sample) {
          await new Promise((r) => setTimeout(r, 900));
          if (mine !== run.current) return;
          const id = `${card.proposal_id}:${card.hunk.id}v2`;
          setSampleDeck((d) => ({ ...d, cards: d.cards.map((c) => (c.id === card.id ? { ...c, id, hunk: { ...c.hunk, id: `${c.hunk.id}v2`, after: SAMPLE_REWRITE.after, tokens: SAMPLE_REWRITE.tokens } } : c)) }));
          const used = [picked.length && plural(picked.length, "page"), marks.length && plural(marks.length, "marked passage")].filter(Boolean).join(" and ");
          setRevised({ cardId: id, version: 2, instruction: cmd.text, reply: used ? `${SAMPLE_REWRITE.reply} (with the ${used} you gave it)` : SAMPLE_REWRITE.reply, prevAfter: card.hunk.after });
          setFocusId(id);
        } else {
          const res = await api.rewrite(card.proposal_id, card.hunk.id, cmd.text, { marks, pages: picked.map((p) => p.slug) });
          if (mine !== run.current) return;
          if (res.unchanged) return setEditError("Nothing changed: say it more specifically?");
          await refetch();
          const id = `${card.proposal_id}:${res.hunk_id}`;
          setRevised({ cardId: id, version: res.proposal.revision ?? 2, instruction: cmd.text, reply: res.reply, prevAfter: card.hunk.after });
          setFocusId(id);
          if (res.others_changed.length) setAnnounce(`${plural(res.others_changed.length, "other card")} of this proposal changed too`);
        }
        setVsPrev(false);
        edit.current?.clear();
      } else if (cmd.kind === "merge") {
        if (!cmd.target) return setEditError("Say which page: /merge @page");
        setBusy(`Merging ${cmd.target} into this page…`);
        if (sample) return setEditError(`In your KB this adds a proposal: ${cmd.target} merged into ${slug}, its links rewritten, as cards here.`);
        const p = await api.merge([slug, cmd.target], slug);
        if (mine !== run.current) return;
        await refetch();
        setAnnounce(`Merge proposal added: ${plural(p.hunks.length, "card")}`);
        if (p.hunks[0]) setFocusId(`${p.id}:${p.hunks[0].id}`);
      } else if (cmd.kind === "split") {
        setBusy("Finding where to split…");
        if (sample) return setEditError("In your KB the model picks where to cut this page and the parts arrive as cards here.");
        const r = await api.split(slug, cmd.hint);
        if (mine !== run.current) return;
        await refetch();
        setAnnounce(r.reply);
        setRevised(null);
        if (r.proposal.hunks[0]) setFocusId(`${r.proposal.id}:${r.proposal.hunks[0].id}`);
      }
    } catch (e) {
      if (mine === run.current) setEditError(`Couldn't do it: ${e instanceof Error ? e.message : String(e)}.`);
    } finally {
      if (mine === run.current) setBusy(null);
    }
  }, [card, sample, api, refetch, marks, picked]);

  // --- the queue: everything ingested; a source that finishes reading brings its cards into the deck ----------------------
  const jobsQ = useApiQuery(["ingest-list"], (d) => d.listIngest(), {
    enabled: !sample,
    refetchInterval: (q) => (q.state.data?.some((j) => j.status === "running") ? 2000 : 15_000),
  });
  const jobs = sample ? SAMPLE_JOBS : (jobsQ.data ?? []);
  const reading = useRef(new Set<string>());
  useEffect(() => {
    if (sample || !jobsQ.data) return;
    const now = new Set(jobsQ.data.filter((j) => j.status === "running").map((j) => j.id));
    const finished = [...reading.current].some((id) => !now.has(id));
    reading.current = now;
    if (finished) void refetch();
  }, [jobsQ.data, sample, refetch]);
  const waiting = useMemo(() => {
    const m = new Map<string, number>();
    for (const c of cards) if (!(c.id in state.decisions) && !state.later.includes(c.id)) m.set(c.proposal_id, (m.get(c.proposal_id) ?? 0) + 1);
    return m;
  }, [cards, state]);
  const queue = useMemo(() => queueRows(jobs, waiting), [jobs, waiting]);
  const runningCount = queue.filter((r) => r.group === "running" && !r.failed).length;
  const [queueOpen, setQueueOpen] = useState(false);
  const onFilter = useCallback((row: QueueRow) => {
    setFilter((f) => (f?.proposalId === row.proposalId || !row.proposalId ? null : { proposalId: row.proposalId, label: row.name }));
    setOffset(0);
    setQueueOpen(false);
  }, []);
  const onStarted = useCallback(() => void qc.invalidateQueries({ queryKey: ["ingest-list"] }), [qc]);
  useEffect(() => {
    if (filter && deck && !cards.some((c) => c.proposal_id === filter.proposalId)) setFilter(null);
  }, [filter, deck, cards]);

  const back = revised && card && revised.cardId === card.id && revised.version > 1 && !sample
    ? async () => {
        try {
          const p = await api.revert(card.proposal_id);
          await refetch();
          const h = p.hunks.find((x) => x.slug === card.hunk.slug && x.at === card.hunk.at) ?? p.hunks[0];
          setRevised(null);
          if (h) setFocusId(`${p.id}:${h.id}`);
        } catch (e) {
          setEditError(`Couldn't go back: ${e instanceof Error ? e.message : String(e)}.`);
        }
      }
    : null;

  // --- apply ---------------------------------------------------------------------------------------------------------
  const [applyOpen, setApplyOpen] = useState(false);
  const [phase, setPhase] = useState<ApplyPhase>({ phase: "plan" });
  const openApply = useCallback(() => {
    if (!rows.length || readOnly) return;
    setPhase({ phase: "plan" });
    setApplyOpen(true);
  }, [rows.length, readOnly]);
  const confirm = async () => {
    setPhase({ phase: "running" });
    if (sample) {
      await new Promise((r) => setTimeout(r, 700));
      const applied = rows.filter((r) => r.outcome === "apply").map((r) => ({ id: r.proposal.id, title: r.proposal.title, commit: "sample", pages: [...new Set(cards.filter((c) => c.proposal_id === r.proposal.id).map((c) => c.hunk.slug))] }));
      setPhase({ phase: "done", outcome: { applied, rejected: rows.filter((r) => r.outcome === "reject").map((r) => r.proposal.id), waiting: [], failed: [] } });
      return;
    }
    try {
      const outcome = await api.apply(batchOf(cards, state, rows));
      setPhase({ phase: "done", outcome });
      await refetch();
    } catch (e) {
      setPhase({ phase: "failed", error: e instanceof Error ? e.message : String(e) });
    }
  };

  // --- keys ----------------------------------------------------------------------------------------------------------
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (applyOpen || typing(e.target)) return;
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") return void (e.preventDefault(), openApply());
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const k = e.key;
      const hit = (fn: () => void) => {
        e.preventDefault();
        fn();
      };
      if (k === "a" || k === "ArrowRight") hit(() => void act(item?.kind === "cover" ? "open" : "accept"));
      else if (k === "r" || k === "ArrowLeft") hit(() => void act("reject"));
      else if (k === "s" || k === "ArrowDown") hit(() => void act("later"));
      else if (k === "o" || k === "Enter") hit(() => void act(item?.kind === "cover" ? "accept" : "open"));
      else if (k === "e") hit(() => edit.current?.focus());
      else if (k === "/") hit(() => edit.current?.focus("/"));
      else if (k === "z") hit(takeBack);
      else if (k === " ") hit(() => setExpanded((x) => !x));
      else if (k === "j") hit(() => setOffset((i) => Math.min(i + 1, items.length - 1)));
      else if (k === "k") hit(() => setOffset((i) => Math.max(i - 1, 0)));
      else if (k === "?") hit(() => setKeysOpen((x) => !x));
      else if (k === "g") hit(() => graph.current?.focusSearch());
      else if (k === "m") hit(markSelection);
      else if (k === "[") hit(() => graph.current?.move(-1));
      else if (k === "]") hit(() => graph.current?.move(1));
      else if (k === "x") hit(() => graph.current?.toggleFocused());
      else if (k === "q" && !wide) hit(() => setQueueOpen((x) => !x));
      else if (k === "Escape" && queueOpen) hit(() => setQueueOpen(false));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [act, takeBack, openApply, applyOpen, item, items.length, markSelection, wide, queueOpen]);

  // --- dropped files ----------------------------------------------------------------------------------------------------
  const [dropped, setDropped] = useState<File | null>(null);
  const [dropping, setDropping] = useState(false);

  if (!sample && deckQ.isError) return <div className="mx-auto max-w-3xl p-6"><ErrorState title="Could not load the review deck" error={deckQ.error} onRetry={() => void deckQ.refetch()} /></div>;
  if (!deck) return <div className="mx-auto max-w-3xl p-6"><Loading label="Loading the review deck" /></div>;

  const accentBorder = dx > 40 ? "border-ok/60" : dx < -40 ? "border-foreground/30" : "";
  const dragShare = Math.min(1, Math.abs(dx) / 220);
  const reachPanel = card ? (
    <ReachGraph ref={graph} cardId={card.id} center={{ title: card.page_title, isNew: card.hunk.op === "create_page" }} reach={card.reach} selected={picked} onToggle={togglePick} search={searchGraph} />
  ) : (
    <p className="pt-2 text-xs text-muted-foreground">{item?.kind === "stack" ? "Open the stack to see what each change touches." : item ? "Review the source's cards to see what each one touches." : ""}</p>
  );
  const queuePanel = (
    <Queue rows={queue} loading={!sample && jobsQ.isLoading} current={card?.proposal_id ?? null} filter={filter?.proposalId ?? null} onFilter={onFilter} readOnly={readOnly} sample={sample} dropped={dropped} onStarted={onStarted} />
  );
  const queueLabel = `Queue${runningCount ? ` · ${runningCount} running` : ""}`;
  return (
    <div
      className={cn("mx-auto w-full max-w-[1400px] px-4 py-6", dropping && "rounded-xl outline-dashed outline-2 outline-primary/40")}
      onDragOver={(e) => { if (e.dataTransfer.types.includes("Files")) { e.preventDefault(); setDropping(true); } }}
      onDragLeave={() => setDropping(false)}
      onDrop={(e) => { const f = e.dataTransfer.files?.[0]; if (f) { e.preventDefault(); setDropped(f); setQueueOpen(true); } setDropping(false); }}
    >
      <style>{`::highlight(${HIGHLIGHT}){background-color:rgb(254 243 199);color:inherit}`}</style>
      <div className={cn("grid gap-6", wide ? "grid-cols-[280px_minmax(560px,720px)_300px] justify-center" : medium ? "grid-cols-[280px_minmax(0,1fr)_40px]" : "grid-cols-1")}>
      {medium && <aside className="sticky top-4 self-start" aria-label="What this card touches">{reachPanel}</aside>}
      <main className="flex min-w-0 flex-col gap-4">
      <header className="flex flex-wrap items-center gap-3">
        <div className="mr-auto">
          <h1 className="text-lg font-semibold">Review{sample && <span className="ml-2 text-sm font-normal text-muted-foreground">sample deck · nothing is saved</span>}</h1>
          <p className="text-xs text-muted-foreground">
            {cards.length ? `${plural(cards.length - decided - state.later.length, "change")} waiting · ${decided} decided` : "Nothing to review"}
            {readOnly && " · view only: this knowledge base can't be changed here"}
          </p>
        </div>
        {state.later.length > 0 && (
          <Button variant="ghost" size="sm" onClick={() => setState(reviewLater)} title="Put the cards left for later back in the deck">
            <Clock aria-hidden /> Later {state.later.length}
          </Button>
        )}
        <Button variant="ghost" size="sm" onClick={takeBack} disabled={!state.history.length} aria-keyshortcuts="z" title="Undo (Z)">
          <Undo2 aria-hidden /> Undo
        </Button>
        <Button size="sm" onClick={openApply} disabled={!rows.length || readOnly} data-tour="review-apply" aria-keyshortcuts="Meta+Enter" title="Apply (⌘↵)">
          Apply {accepted || ""}{steps > 1 ? ` (${steps} steps)` : ""}
        </Button>
        {!medium && (
          <Button variant="outline" size="sm" onClick={() => setQueueOpen(true)} aria-keyshortcuts="q" title="Queue (Q)">
            <Inbox aria-hidden /> {queueLabel}
          </Button>
        )}
      </header>

      {filter && (
        <div className="flex items-center gap-2 rounded-md bg-accent/60 px-3 py-1.5 text-xs" role="status">
          <span>Showing {plural(shown.length, "card")} from {filter.label}</span>
          <button type="button" className="underline underline-offset-2" onClick={() => setFilter(null)}>Show all</button>
        </div>
      )}
      {!medium && card && (
        <details className="group rounded-lg border px-3 py-2">
          <summary className="flex cursor-pointer list-none items-center gap-1 text-sm">
            Touches {plural(card.reach?.total ?? 0, "page")} <ChevronDown className="size-3.5 transition-transform group-open:rotate-180" aria-hidden />
          </summary>
          <div className="pt-2">{reachPanel}</div>
        </details>
      )}

      {item ? (
        <div
          ref={cardEl}
          className={cn("relative touch-pan-y select-text rounded-xl border bg-card p-6 shadow-[var(--shadow)] transition-colors", accentBorder)}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
        >
          {dx !== 0 && (
            <span className={cn("pointer-events-none absolute top-3 text-sm font-semibold uppercase tracking-wide", dx > 0 ? "right-4 text-ok" : "left-4 text-muted-foreground")} style={{ opacity: dragShare }} aria-hidden>
              {dx > 0 ? "Accept" : "Reject"}
            </span>
          )}
          {item.kind === "card" && (
            <ChangeCard card={item.card} position={position} expanded={expanded} revised={revised?.cardId === item.card.id ? revised : null} vsPrev={vsPrev} onVsPrev={setVsPrev} onBack={back} />
          )}
          {item.kind === "stack" && <StackCard klass={item.klass} cards={item.cards} position={position} />}
          {item.kind === "cover" && <CoverCard source={item.source} newPages={item.newPages} changes={item.changes} position={position} />}

          <div className="mt-5 flex flex-wrap items-center gap-2" data-tour="review-actions">
            {item.kind === "cover" ? (
              <>
                <Button variant="outline" onClick={() => void act("later")} disabled={readOnly} aria-keyshortcuts="s"><Clock aria-hidden /> Later <Kbd>S</Kbd></Button>
                <Button className="ml-auto bg-ok/15 text-ok hover:bg-ok/25" variant="secondary" onClick={() => void act("accept")} disabled={readOnly} aria-keyshortcuts="a">Review its cards <Kbd>A</Kbd></Button>
              </>
            ) : (
              <>
                <Button variant="outline" onClick={() => void act("reject")} disabled={readOnly} aria-keyshortcuts="r"><X aria-hidden /> {item.kind === "stack" ? "Reject all" : "Reject"} <Kbd>R</Kbd></Button>
                <Button variant="ghost" onClick={() => void act("later")} disabled={readOnly} aria-keyshortcuts="s"><Clock aria-hidden /> Later <Kbd>S</Kbd></Button>
                {item.kind === "stack" ? (
                  <Button variant="ghost" onClick={() => void act("open")} aria-keyshortcuts="o">Open <Kbd>O</Kbd></Button>
                ) : (
                  <Button variant="ghost" onClick={() => edit.current?.focus()} disabled={readOnly} aria-keyshortcuts="e"><Pencil aria-hidden /> Edit <Kbd>E</Kbd></Button>
                )}
                <Button className="ml-auto bg-ok/15 text-ok hover:bg-ok/25" variant="secondary" onClick={() => void act("accept")} disabled={readOnly} aria-keyshortcuts="a">
                  <Check aria-hidden /> {item.kind === "stack" ? "Accept all" : "Accept"} <Kbd>A</Kbd>
                </Button>
              </>
            )}
          </div>
          {item.kind === "card" && (
            <div className="mt-3">
              <EditLine
                ref={edit}
                busy={busy}
                error={editError}
                disabled={readOnly || !["edit_page", "create_page"].includes(item.card.hunk.op)}
                disabledReason={readOnly ? "View only" : "This kind of change can only be accepted or rejected"}
                slug={item.card.hunk.slug}
                findPages={api.mentions}
                context={context}
                suggested={suggested}
                onRemovePage={(slug) => setPicked((s) => s.filter((p) => p.slug !== slug))}
                onRemoveMark={(i) => setMarks((m) => m.filter((_, j) => j !== i))}
                onClearContext={() => { setPicked([]); setMarks([]); }}
                onSubmit={(c) => void submit(c)}
                onCancel={() => { run.current++; setBusy(null); }}
              />
            </div>
          )}
        </div>
      ) : (
        <Done laterCount={state.later.length} accepted={accepted} canApply={rows.length > 0 && !readOnly} onLater={() => setState(reviewLater)} onApply={openApply} />
      )}

      <footer className="flex items-center gap-3 text-xs text-muted-foreground">
        <button type="button" className="flex items-center gap-1 hover:text-foreground" onClick={() => setKeysOpen((x) => !x)} aria-expanded={keysOpen}>
          <Keyboard className="size-3.5" aria-hidden /> Keys <Kbd>?</Kbd>
        </button>
        <span>Drag a card right to accept, left to reject.</span>
      </footer>
      {keysOpen && (
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 rounded-lg border p-3 text-xs" aria-label="Keys">
          {KEYS.map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="font-mono text-muted-foreground">{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
      )}
      </main>
      {wide && <aside className="sticky top-4 max-h-[calc(100vh-2rem)] self-start overflow-y-auto">{queuePanel}</aside>}
      {medium && !wide && (
        <button type="button" onClick={() => setQueueOpen(true)} className="sticky top-4 flex flex-col items-center gap-1 self-start rounded-md border py-2 text-xs text-muted-foreground hover:text-foreground" aria-label={queueLabel} title="Queue (Q)">
          <Inbox className="size-4" aria-hidden />
          {runningCount > 0 && <span className="font-medium text-foreground">{runningCount}</span>}
        </button>
      )}
      </div>
      {!wide && queueOpen && (
        <div className="fixed inset-0 z-40 flex justify-end bg-black/20" onClick={() => setQueueOpen(false)}>
          <div className="h-full w-[320px] max-w-full overflow-y-auto border-l bg-background p-4 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="mb-2 flex justify-end">
              <Button variant="ghost" size="sm" onClick={() => setQueueOpen(false)} aria-label="Close the queue"><X aria-hidden /></Button>
            </div>
            {queuePanel}
          </div>
        </div>
      )}
      {pill && item?.kind === "card" && !readOnly && (
        <button
          type="button"
          className="fixed z-50 flex -translate-x-1/2 -translate-y-full items-center gap-1 rounded-full border bg-popover px-2.5 py-1 text-xs shadow-md disabled:opacity-70"
          style={{ left: pill.x, top: pill.y - 6 }}
          disabled={marks.length >= MAX_MARKS}
          onMouseDown={(e) => e.preventDefault()}
          onClick={markSelection}
        >
          {marks.length >= MAX_MARKS ? `${MAX_MARKS} marks is the limit` : <>Add to edit <Kbd>M</Kbd></>}
        </button>
      )}
      <p className="sr-only" aria-live="polite">{announce}</p>
      <ApplyDialog open={applyOpen} onOpenChange={setApplyOpen} rows={rows} state={phase} onConfirm={() => void confirm()} />
    </div>
  );
}

function Kbd({ children }: { children: string }) {
  return <kbd className="ml-1 rounded border px-1 font-mono text-[10px] font-normal opacity-70">{children}</kbd>;
}

function Done({ laterCount, accepted, canApply, onLater, onApply }: { laterCount: number; accepted: number; canApply: boolean; onLater: () => void; onApply: () => void }) {
  return (
    <section className="flex flex-col items-center gap-3 rounded-xl border bg-card px-6 py-12 text-center" data-tour="review-card">
      <h2 className="text-lg font-semibold">All caught up.</h2>
      {accepted > 0 && <p className="text-sm text-muted-foreground">{plural(accepted, "accepted change")} ready to apply.</p>}
      <div className="flex flex-wrap justify-center gap-2">
        {canApply && <Button onClick={onApply}>Apply</Button>}
        {laterCount > 0 && <Button variant="outline" onClick={onLater}>Review the {plural(laterCount, "card")} left for later</Button>}
      </div>
      <p className="text-xs text-muted-foreground">
        Add knowledge: drop a file or paste a link in the queue, or open <Link to={"/ingest" as "/"} className="underline underline-offset-2">Ingest</Link>. See it on the{" "}
        <Link to={"/graph" as "/"} className="underline underline-offset-2">graph</Link>.
      </p>
    </section>
  );
}
