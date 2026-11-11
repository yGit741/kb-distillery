import { ArrowLeft, ChevronLeft, ChevronRight, Shield, X } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { SAMPLE_ITEM, SAMPLE_QUEUE } from "./fixtures";
import {
  applyCount,
  bulkCount,
  bulkLabel,
  changesOf,
  groupsOf,
  isChange,
  lookPages,
  openOf,
  openOnPage,
  pageDone,
  pageSummary,
  type Change,
  type Choice,
  type Decision,
  type PreviewItem,
  type PreviewPage,
  type QueueEntry,
} from "./model";
import { useEditPreview } from "./store";
import { TouchedGraph } from "./TouchedGraph";

/** New text: a soft green wash, never a red or a strike-through colour. */
const INS = "rounded-[3px] bg-[color-mix(in_srgb,var(--ok)_12%,transparent)] px-0.5 no-underline";
const LINK = "text-sm text-primary hover:underline disabled:pointer-events-none disabled:opacity-50";
const QUIET = "text-xs text-muted-foreground underline";

const ProtectedMark = () => (
  <Shield aria-label="Protected page" className="inline size-3.5 shrink-0 align-[-2px] text-muted-foreground" />
);

/** One question, one picked answer. */
function Pick({ c }: { c: Choice }) {
  const picked = useEditPreview((s) => s.decisions.choices[c.id] ?? c.picked);
  const pick = useEditPreview((s) => s.pick);
  return (
    <div className="max-w-[68ch] border-b py-3 last:border-b-0">
      <div className="text-sm font-medium">{c.title}</div>
      <div className="mb-2 text-xs text-muted-foreground">{c.why}</div>
      <div role="radiogroup" aria-label={c.title} className="inline-flex rounded-md bg-muted p-0.5">
        {c.options.map((o, i) => (
          <button key={o} type="button" role="radio" aria-checked={i === picked} onClick={() => pick(c.id, i)} className={cn("rounded px-2.5 py-0.5 text-xs", i === picked ? "bg-card shadow-[var(--shadow)]" : "text-muted-foreground")}>
            {o}
          </button>
        ))}
      </div>
    </div>
  );
}

function Group({ title, count, note, action, children }: { title: string; count: string; note?: string; action?: ReactNode; children?: ReactNode }) {
  return (
    <section aria-label={title} className="mb-6 max-w-[76ch]">
      <div className="flex items-baseline gap-2.5 border-b pb-1">
        <h3 className="text-sm font-semibold">{title}</h3>
        <span className="text-xs text-muted-foreground">{count}</span>
        {action && <span className="ml-auto">{action}</span>}
      </div>
      {note && <p className="mb-1 mt-1.5 text-xs text-muted-foreground">{note}</p>}
      {children}
    </section>
  );
}

function ChangeText({ c, decision }: { c: Change; decision?: Decision }) {
  if (decision === "rejected") return <span className="text-muted-foreground">{c.before ?? c.after}</span>;
  return (
    <>
      {c.before && !decision && <del className="text-muted-foreground">{c.before} </del>}
      {decision ? <span>{c.after}</span> : <ins className={INS}>{c.after}</ins>}
    </>
  );
}

const said = (d: Decision) => (d === "accepted" ? "accepted" : "rejected");

/** Every change in groups: the easy ones are cleared here, the rest open in the page. */
function AllChanges({ item }: { item: PreviewItem }) {
  const s = useEditPreview();
  const d = s.decisions;
  const g = groupsOf(item);
  const open = openOf(item, d);
  const apply = applyCount(item, d);
  const bulkPagesDone = g.bulk.every((p) => d.bulk[p.slug]);
  const row = (page: PreviewPage, key: string, text: ReactNode, right: ReactNode) => (
    <div key={key} className="grid grid-cols-[9.5rem_1fr_auto] items-baseline gap-3 border-b py-2 text-sm last:border-b-0">
      <span className="text-muted-foreground">
        {page.protected && <ProtectedMark />} {page.title}
      </span>
      <span>{text}</span>
      <span className="flex items-baseline gap-3 whitespace-nowrap">{right}</span>
    </div>
  );
  if (s.applied)
    return (
      <div className="pt-10">
        <h2 className="text-xl font-semibold">Nothing was written</h2>
        <p className="mt-1 max-w-[60ch] text-sm text-muted-foreground">
          This preview runs on sample data. Your {apply.changes} accepted changes on {apply.pages} pages would land as one commit you can undo.
        </p>
        <Button variant="outline" size="sm" className="mt-4" onClick={s.reset}>
          Start over
        </Button>
      </div>
    );
  return (
    <>
      <h2 className="text-xl font-semibold">{item.title}</h2>
      <p className="mb-5 text-sm text-muted-foreground">Clear the easy groups here. Open the ones that need a look.</p>
      {item.before.length > 0 && (
        <Group title="Before you start" count={`${item.before.length} choices`}>
          {item.before.map((c) => (
            <Pick key={c.id} c={c} />
          ))}
        </Group>
      )}
      <Group title="Needs a look" count={open.look ? `${open.look} open` : "done"} note="Rewrites of what a page says, and every change on a protected page. These open in the page.">
        {g.look.map(({ page, change }) => {
          const dec = d.changes[change.id];
          return row(
            page,
            change.id,
            <ChangeText c={change} decision={dec} />,
            <>
              {dec && <span className="text-xs text-muted-foreground">{said(dec)}</span>}
              <button type="button" className={LINK} onClick={() => s.showPage(page.slug, change.id)}>
                Open
              </button>
            </>,
          );
        })}
        {g.lookBulk.map((page) =>
          row(
            page,
            `bulk-${page.slug}`,
            <span className="text-muted-foreground">{bulkLabel(page)}</span>,
            <>
              {d.bulk[page.slug] && <span className="text-xs text-muted-foreground">{said(d.bulk[page.slug]!)}</span>}
              <button type="button" className={LINK} onClick={() => s.showPage(page.slug)}>
                Open
              </button>
            </>,
          ),
        )}
      </Group>
      {g.additions.length > 0 && (
        <Group
          title="Additions"
          count={open.additions ? `${open.additions} open` : "done"}
          note="New sentences and new pages. Nothing you already have is changed."
          action={
            open.additions > 0 && (
              <button type="button" className={LINK} onClick={() => s.acceptAdditions(item)}>
                Accept all {open.additions}
              </button>
            )
          }
        >
          {g.additions.map(({ page, change }) => {
            const dec = d.changes[change.id];
            return row(
              page,
              change.id,
              <ChangeText c={change} decision={dec} />,
              dec ? (
                <>
                  <span className="text-xs text-muted-foreground">{said(dec)}</span>
                  <button type="button" className={QUIET} onClick={() => s.decide(change.id, null)}>
                    undo
                  </button>
                </>
              ) : (
                <>
                  <button type="button" className={LINK} onClick={() => s.decide(change.id, "accepted")}>
                    Accept
                  </button>
                  <button type="button" className="text-sm text-muted-foreground hover:underline" onClick={() => s.decide(change.id, "rejected")}>
                    Reject
                  </button>
                </>
              ),
            );
          })}
        </Group>
      )}
      {g.bulk.length > 0 && (
        <Group
          title="Links and fixes"
          count={open.bulk ? `${open.bulk} open` : "done"}
          note={`On ${g.bulk.map((p) => p.title).join(", ")}. The words you read stay the same.`}
          action={
            open.bulk > 0 ? (
              <button type="button" className={LINK} onClick={() => s.acceptBulk(item)}>
                Accept all {open.bulk}
              </button>
            ) : (
              bulkPagesDone && (
                <button type="button" className={QUIET} onClick={() => g.bulk.forEach((p) => s.decideBulk(p.slug, null))}>
                  undo
                </button>
              )
            )
          }
        />
      )}
      {item.leftOut.length > 0 && (
        <Group title="Left out" count={`${item.leftOut.length} claims`} note="Claims from the source that landed on no page.">
          {item.leftOut.map((c) => (
            <Pick key={c.id} c={c} />
          ))}
        </Group>
      )}
      <div className="flex max-w-[76ch] items-center gap-3 pb-2">
        <span className="text-sm text-muted-foreground">{open.total ? `${open.total} still open` : "Everything is decided. One commit; you can undo it."}</span>
        <Button className="ml-auto" disabled={open.total > 0 || apply.changes === 0} onClick={s.apply}>
          {open.total === 0 && apply.changes === 0 ? "Nothing to apply" : `Apply ${apply.changes} ${apply.changes === 1 ? "change" : "changes"}`}
        </Button>
      </div>
    </>
  );
}

/** One change in the page text: a margin bar and a label; the focused one shows its source and the three actions. */
function ChangeBlock({ c, focused }: { c: Change; focused: boolean }) {
  const dec = useEditPreview((s) => s.decisions.changes[c.id]);
  const decide = useEditPreview((s) => s.decide);
  const focus = useEditPreview((s) => s.focus);
  const open = focused && !dec;
  return (
    <div
      data-testid={`change-${c.id}`}
      data-focused={open || undefined}
      onClick={() => !dec && focus(c.id)}
      className={cn(
        "relative mb-3.5 max-w-[68ch] border-l-2 pl-3.5",
        dec ? "border-border" : c.kind === "rewrite" ? "cursor-pointer border-l-[3px] border-foreground/60" : "cursor-pointer border-[color-mix(in_srgb,var(--ok)_55%,transparent)]",
        open && "rounded-r-lg bg-muted py-2 pr-2.5",
      )}
    >
      <span className="absolute -left-[4.75rem] top-0.5 w-14 text-right text-[11px] text-muted-foreground">{c.kind}</span>
      <ChangeText c={c} decision={dec} />
      {dec && (
        <button
          type="button"
          className={cn(QUIET, "ml-2")}
          onClick={(e) => {
            e.stopPropagation();
            decide(c.id, null);
            focus(c.id);
          }}
        >
          {dec === "rejected" ? "rejected, undo" : "undo"}
        </button>
      )}
      {open && (
        <div className="mt-2">
          <div className="mb-2 text-xs text-muted-foreground">{c.quote}</div>
          <div className="flex gap-1.5" onClick={(e) => e.stopPropagation()}>
            <Button size="sm" onClick={() => decide(c.id, "accepted")}>
              Accept
            </Button>
            <Button size="sm" variant="outline" onClick={() => decide(c.id, "rejected")}>
              Reject
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

/** The page as a document, with its changes in place. */
function PageDoc({ item, page, focus }: { item: PreviewItem; page: PreviewPage; focus: string | null }) {
  const s = useEditPreview();
  const d = s.decisions;
  const setFocus = useEditPreview((st) => st.focus);
  const [similar, setSimilar] = useState(false);
  const firstOpen = changesOf(page).find((c) => !d.changes[c.id])?.id ?? null;
  const focused = focus && !d.changes[focus] ? focus : firstOpen;
  const left = openOnPage(page, d);
  const bulkDec = d.bulk[page.slug];
  const pages = lookPages(item);
  const at = pages.findIndex((p) => p.slug === page.slug);
  const next = pages.slice(at + 1).find((p) => !pageDone(p, d)) ?? pages.find((p) => !pageDone(p, d) && p.slug !== page.slug);
  const onward = () => (next ? s.showPage(next.slug) : s.showAll());

  // j / k step through the open changes of the page, like the arrows of a reader
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.key !== "j" && e.key !== "k") || e.metaKey || e.ctrlKey || e.altKey) return;
      if ((e.target as HTMLElement).closest("input, textarea, select, [contenteditable]")) return;
      const open = changesOf(page).filter((c) => !useEditPreview.getState().decisions.changes[c.id]);
      if (!open.length) return;
      const i = open.findIndex((c) => c.id === focused);
      setFocus(open[Math.max(0, Math.min(open.length - 1, i + (e.key === "j" ? 1 : -1)))]!.id);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [page, focused, setFocus]);

  return (
    <>
      <h2 className="text-xl font-semibold">
        {page.protected && <ProtectedMark />} {page.title}
      </h2>
      <p className="mb-4 text-sm text-muted-foreground">{[page.isNew ? "New page" : "", pageSummary(page), page.protected ? "protected: decide each change" : ""].filter(Boolean).join(" · ")}</p>
      {page.body.map((b, i) =>
        isChange(b) ? (
          <ChangeBlock key={b.id} c={b} focused={focused === b.id} />
        ) : (
          <p key={i} className="mb-3.5 max-w-[68ch]">
            {b}
          </p>
        ),
      )}
      {bulkCount(page) > 0 && (
        <div className="mt-4 flex max-w-[68ch] items-baseline gap-3 border-t py-2.5 text-sm">
          <span>{bulkLabel(page)}</span>
          <span className="ml-auto flex items-baseline gap-3">
            {bulkDec ? (
              <>
                <span className="text-xs text-muted-foreground">{said(bulkDec)}</span>
                <button type="button" className={QUIET} onClick={() => s.decideBulk(page.slug, null)}>
                  undo
                </button>
              </>
            ) : (
              <>
                <button type="button" className={LINK} onClick={() => s.decideBulk(page.slug, "accepted")}>
                  Accept all
                </button>
                <button type="button" className="text-sm text-muted-foreground hover:underline" onClick={() => s.decideBulk(page.slug, "rejected")}>
                  Reject
                </button>
              </>
            )}
          </span>
        </div>
      )}
      {page.similar.length > 0 && (
        <div className="max-w-[68ch] border-t py-2.5 text-sm">
          <button type="button" className={LINK} aria-expanded={similar} onClick={() => setSimilar((v) => !v)}>
            {page.similar.length} similar {page.similar.length === 1 ? "page" : "pages"}
          </button>
          {similar &&
            page.similar.map((x) => (
              <div key={x.slug} className="pt-1">
                <Pick c={{ id: `similar-${page.slug}-${x.slug}`, title: x.title, why: x.why, options: ["Merge", "Link", "Keep apart"], picked: 2 }} />
              </div>
            ))}
        </div>
      )}
      <div className="mt-5 flex max-w-[68ch] items-center gap-3">
        {page.protected && left > 0 && <span className="text-sm text-muted-foreground">{left} still open on this page</span>}
        <span className="ml-auto">
          {page.protected ? (
            <Button disabled={left > 0} onClick={onward}>
              {next ? "Next page" : "Back to all changes"}
            </Button>
          ) : (
            <Button
              onClick={() => {
                s.acceptRest(page);
                onward();
              }}
            >
              {left > 0 ? "Accept the rest and continue" : next ? "Next page" : "Back to all changes"}
            </Button>
          )}
        </span>
      </div>
    </>
  );
}

function Queue({ entries, current }: { entries: QueueEntry[]; current: string }) {
  return (
    <nav aria-label="Queue" className="min-h-0 overflow-auto px-2 py-3">
      <div className="px-2 pb-2 text-xs text-muted-foreground">Queue</div>
      <ul>
        {entries.map((q) => (
          <li key={q.id} aria-current={q.id === current || undefined} className={cn("rounded-lg p-2", q.id === current ? "bg-accent-soft" : "text-muted-foreground")}>
            <div className="text-sm leading-snug">{q.title}</div>
            <div className="text-xs text-muted-foreground">
              {q.note}
              {q.protected && (
                <>
                  {" · "}
                  <ProtectedMark />
                </>
              )}
            </div>
          </li>
        ))}
      </ul>
    </nav>
  );
}

/** The pages arrive one by one while a dropped file is read. */
function useArriving(reading: boolean, n: number): number {
  const [shown, setShown] = useState(reading ? 0 : n);
  const ready = useEditPreview((s) => s.ready);
  useEffect(() => {
    if (!reading) {
      setShown(n);
      return;
    }
    setShown(0);
    const timers = Array.from({ length: n }, (_, i) => setTimeout(() => setShown(i + 1), 300 + i * 260));
    timers.push(setTimeout(ready, 300 + n * 260 + 200));
    return () => timers.forEach(clearTimeout);
  }, [reading, n, ready]);
  return shown;
}

/**
 * The edit preview: one sheet over the graph where every change of one queued item is reviewed before it is
 * applied. Queue | changes or page | graph over chat. Flag ui.edit-preview; sample data until the queue lands.
 */
export function EditPreviewSheet() {
  const s = useEditPreview();
  const item = SAMPLE_ITEM;
  const page = s.view.kind === "page" ? item.pages.find((p) => p.slug === (s.view as { slug: string }).slug) : undefined;
  const shown = useArriving(s.reading, item.pages.length);
  const pages = lookPages(item);
  const at = page ? pages.findIndex((p) => p.slug === page.slug) : -1;
  const step = (by: number) => {
    const to = pages[at + by];
    if (to) s.showPage(to.slug);
  };
  const focusId = s.view.kind === "page" ? s.view.focus : null;
  const about = page ? `About: ${page.title}` : "About: all changes";
  return (
    <Dialog open={s.open} onOpenChange={(o) => !o && s.close()}>
      <DialogContent data-testid="edit-preview" className="left-[7.5vw] top-[7.5vh] grid h-[85vh] w-[85vw] max-w-none translate-x-0 grid-rows-[3rem_1fr] rounded-2xl bg-card text-card-foreground">
        <header className="flex items-center gap-3 border-b px-4">
          <DialogTitle className="text-sm font-semibold">{item.title}</DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground">{item.pages.length} pages · sample data</DialogDescription>
          <button type="button" aria-label="Close" title="Close (keeps your decisions)" onClick={s.close} className="ml-auto grid size-7 place-items-center rounded-lg hover:bg-accent">
            <X className="size-4" />
          </button>
        </header>
        <div className="grid min-h-0 grid-cols-[220px_1fr_340px] divide-x">
          <Queue entries={SAMPLE_QUEUE} current={item.id} />
          <div className="grid min-h-0 grid-rows-[auto_1fr]">
            <div className="flex h-10 items-center gap-1.5 pl-[5.75rem] pr-7 pt-2 text-xs text-muted-foreground">
              {page && !s.reading ? (
                <>
                  <button type="button" className={cn(LINK, "mr-2 inline-flex items-center gap-1 text-xs")} onClick={s.showAll}>
                    <ArrowLeft className="size-3.5" /> All changes
                  </button>
                  <button type="button" aria-label="Previous" disabled={at <= 0} onClick={() => step(-1)} className="grid size-6 place-items-center rounded-md hover:bg-accent disabled:opacity-40">
                    <ChevronLeft className="size-4" />
                  </button>
                  <button type="button" aria-label="Next" disabled={at < 0 || at >= pages.length - 1} onClick={() => step(1)} className="grid size-6 place-items-center rounded-md hover:bg-accent disabled:opacity-40">
                    <ChevronRight className="size-4" />
                  </button>
                  {at >= 0 && (
                    <span className="ml-1">
                      {at + 1} of {pages.length}
                    </span>
                  )}
                </>
              ) : (
                <span>All changes</span>
              )}
            </div>
            <div className="min-h-0 overflow-auto pb-7 pl-[5.75rem] pr-7 pt-2 text-sm leading-relaxed">
              {s.reading ? (
                <p role="status" className="pt-10 text-muted-foreground">
                  Reading the source and finding the pages it touches.
                </p>
              ) : page ? (
                <PageDoc key={page.slug} item={item} page={page} focus={focusId} />
              ) : (
                <AllChanges item={item} />
              )}
            </div>
          </div>
          <div className="grid min-h-0 grid-rows-[45%_55%]">
            <div className="flex min-h-0 flex-col border-b">
              <div className="px-3.5 pb-1 pt-2.5 text-xs text-muted-foreground">Pages this touches</div>
              <TouchedGraph pages={item.pages} shown={shown} current={page?.slug ?? null} done={(p) => pageDone(p, s.decisions)} onPick={(slug) => s.showPage(slug)} />
            </div>
            <div className="grid min-h-0 grid-rows-[1fr_auto]">
              <p className="overflow-auto px-3.5 py-3 text-sm text-muted-foreground">Ask about anything in this review. The chat is not connected yet.</p>
              <div className="px-3 pb-3 pt-2">
                <div className="mb-1 text-[11px] text-muted-foreground">{about}</div>
                <input disabled aria-label="Ask, or say what to change" placeholder="Ask, or say what to change" className="w-full rounded-lg border bg-transparent px-2.5 py-1.5 text-sm disabled:opacity-60" />
              </div>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
