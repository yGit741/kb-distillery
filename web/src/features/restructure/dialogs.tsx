import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { Check, Plus, X } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { useDataSource } from "@/api";
import type { RestructureBlocks, RestructureResult } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useApiQuery } from "@/lib/useApiQuery";
import { cn } from "@/lib/utils";
import { clip, pickRange, toggleCut, type Range } from "./lib";
import { useRestructureStore } from "./store";

/** The open restructure dialog of the page being read (state in `useRestructureStore`). */
export function RestructureDialogs({ slug, title }: { slug: string; title: string }) {
  const open = useRestructureStore((s) => s.open);
  const close = useRestructureStore((s) => s.close);
  useEffect(() => close, [slug, close]);
  return (
    <Dialog open={!!open} onOpenChange={(o) => !o && close()}>
      {open && (
        <DialogContent className="max-h-[80vh] max-w-xl overflow-y-auto">
          {open.kind === "merge" && <MergeBody slug={slug} title={title} seed={open.mentions} />}
          {open.kind === "split" && <SplitBody slug={slug} />}
          {open.kind === "extract" && <ExtractBody slug={slug} />}
        </DialogContent>
      )}
    </Dialog>
  );
}

function Shell({ title, hint, children }: { title: string; hint: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-4 p-5">
      <header className="flex flex-col gap-1">
        <DialogTitle className="text-base font-medium">{title}</DialogTitle>
        <DialogDescription className="text-sm text-muted-foreground">{hint}</DialogDescription>
      </header>
      {children}
    </div>
  );
}

function Done({ result }: { result: RestructureResult }) {
  const close = useRestructureStore((s) => s.close);
  return (
    <div className="flex flex-col gap-2 rounded-lg border bg-muted/40 p-3 text-sm" data-testid="restructure-done">
      <p className="flex items-center gap-2">
        <Check className="size-4 text-muted-foreground" aria-hidden /> Proposal created. Nothing changes until you review it.
      </p>
      <Link to={`/proposals/${encodeURIComponent(result.id)}` as "/"} onClick={close} className="font-medium text-primary hover:underline">
        {result.title} · {result.hunks.length} change{result.hunks.length === 1 ? "" : "s"}
      </Link>
    </div>
  );
}

function Footer({ error, pending, ready, label, onCreate, done }: { error: string | null; pending: boolean; ready: boolean; label: string; onCreate: () => void; done: ReactNode }) {
  const close = useRestructureStore((s) => s.close);
  if (done) return <>{done}</>;
  return (
    <div className="flex flex-col gap-2">
      {error && (
        <p role="alert" className="text-xs text-muted-foreground">
          That did not go through: {error}
        </p>
      )}
      <div className="flex justify-end gap-2">
        <Button variant="ghost" size="sm" onClick={close}>
          Cancel
        </Button>
        <Button size="sm" disabled={!ready || pending} onClick={onCreate}>
          {pending ? "Creating…" : label}
        </Button>
      </div>
    </div>
  );
}

const errText = (e: unknown) => (e instanceof Error ? e.message : String(e));

// -- merge -------------------------------------------------------------------------------------------------------------
function MergeBody({ slug, title, seed }: { slug: string; title: string; seed: string[] }) {
  const ds = useDataSource();
  const qc = useQueryClient();
  const [pages, setPages] = useState<string[]>(() => [slug, ...seed.filter((s) => s !== slug)]);
  const [titles, setTitles] = useState<Record<string, string>>({ [slug]: title });
  const [survivor, setSurvivor] = useState(slug);
  const [q, setQ] = useState("");
  const hits = useApiQuery(["pages", "mentions", q], (d) => d.searchMentions(q), { retry: false, staleTime: 60_000 });
  const ready = pages.length >= 2;
  const preview = useApiQuery(["restructure", "merge-preview", pages, survivor], (d) => d.getMergePreview(pages, survivor), { enabled: ready, retry: false });
  const make = useMutation({
    mutationFn: () => ds.restructureMerge({ slugs: pages, survivor }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["proposals"] }),
  });
  const add = (s: string, t: string) => {
    setPages((p) => (p.includes(s) ? p : [...p, s]));
    setTitles((m) => ({ ...m, [s]: t }));
    setQ("");
  };
  const remove = (s: string) => {
    setPages((p) => p.filter((x) => x !== s));
    if (survivor === s) setSurvivor(slug);
  };
  const ripple = preview.data?.ripple ?? [];
  const others = pages.filter((p) => p !== survivor);
  return (
    <Shell title="Merge pages" hint="Pick the pages that grew into one topic and which slug survives. The others become tombstones that redirect to it.">
      <ul className="flex flex-col gap-1" aria-label="Pages to merge">
        {pages.map((s) => (
          <li key={s} className="flex items-center gap-2 rounded-md border px-2 py-1.5 text-sm">
            <input type="radio" name="survivor" id={`survivor-${s}`} checked={survivor === s} onChange={() => setSurvivor(s)} aria-label={`Keep ${s}`} />
            <label htmlFor={`survivor-${s}`} className="min-w-0 flex-1 truncate">
              {titles[s] ?? s} <span className="text-xs text-muted-foreground">{s}</span>
            </label>
            {survivor === s && <span className="text-xs text-muted-foreground">survives</span>}
            {s !== slug && (
              <button type="button" aria-label={`Remove ${s}`} className="rounded p-0.5 text-muted-foreground hover:text-foreground" onClick={() => remove(s)}>
                <X className="size-3.5" />
              </button>
            )}
          </li>
        ))}
      </ul>
      <div className="relative">
        <Input aria-label="Add a page" placeholder="Add a page to merge…" value={q} onChange={(e) => setQ(e.target.value)} />
        {q.trim() && (hits.data ?? []).filter((h) => !pages.includes(h.slug)).length > 0 && (
          <ul role="listbox" aria-label="Pages" className="absolute left-0 right-0 top-full z-10 mt-1 max-h-48 overflow-y-auto rounded-md border bg-card p-1 shadow-md">
            {(hits.data ?? [])
              .filter((h) => !pages.includes(h.slug))
              .map((h) => (
                <li key={h.slug} role="option" aria-selected={false} onMouseDown={(e) => (e.preventDefault(), add(h.slug, h.title))} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 text-sm hover:bg-muted">
                  <Plus className="size-3.5 text-muted-foreground" aria-hidden /> @{h.slug} <span className="truncate text-xs text-muted-foreground">{h.title}</span>
                </li>
              ))}
          </ul>
        )}
      </div>
      <section aria-label="Ripple" className="min-h-[3.5rem] rounded-md bg-muted/40 p-3 text-sm">
        {!ready && <p className="text-muted-foreground">Add at least one more page to see which links would be rewritten.</p>}
        {ready && preview.isPending && <p className="text-muted-foreground">Checking links…</p>}
        {ready && preview.isError && <p className="text-muted-foreground">Could not check the links.</p>}
        {ready && preview.data && (
          <>
            <p data-testid="ripple-summary">
              {ripple.length === 0 ? "No other page links to " : `${ripple.length} page${ripple.length === 1 ? "" : "s"} will have links rewritten to `}
              {ripple.length === 0 ? others.join(", ") : survivor}.
            </p>
            {ripple.length > 0 && (
              <ul className="mt-1 max-h-28 overflow-y-auto text-xs text-muted-foreground">
                {ripple.map((r) => (
                  <li key={r.slug}>
                    {r.slug} · {r.links} link{r.links === 1 ? "" : "s"}
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </section>
      <Footer
        error={make.isError ? errText(make.error) : null}
        pending={make.isPending}
        ready={ready}
        label="Create proposal"
        onCreate={() => make.mutate()}
        done={make.data && <Done result={make.data} />}
      />
    </Shell>
  );
}

// -- block lists (split, extract) -----------------------------------------------------------------------------------------
function useBlocks(slug: string) {
  return useApiQuery<RestructureBlocks>(["restructure", "blocks", slug], (d) => d.getRestructureBlocks(slug), { retry: false, gcTime: 0 });
}

function BlocksState({ q, children }: { q: ReturnType<typeof useBlocks>; children: (b: RestructureBlocks) => ReactNode }) {
  if (q.isPending) return <p className="min-h-[6rem] text-sm text-muted-foreground">Loading the page blocks…</p>;
  if (q.isError || !q.data)
    return (
      <p role="alert" className="text-sm text-muted-foreground">
        Could not read the page blocks. <button type="button" className="underline" onClick={() => void q.refetch()}>Try again</button>
      </p>
    );
  return <>{children(q.data)}</>;
}

const BLOCK = "rounded-md px-2 py-1.5 text-sm leading-snug";
const kindClass = (kind: string) => (kind === "heading" ? "font-medium" : "text-muted-foreground");

// -- split: the cut view ---------------------------------------------------------------------------------------------------
function SplitBody({ slug }: { slug: string }) {
  const ds = useDataSource();
  const qc = useQueryClient();
  const q = useBlocks(slug);
  const [cuts, setCuts] = useState<number[]>([]);
  const [names, setNames] = useState<Record<number, string>>({});
  const make = useMutation({
    mutationFn: () => ds.restructureSplit({ slug, cuts, titles: cuts.map((c) => (names[c] ?? "").trim()) }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["proposals"] }),
  });
  const ready = cuts.length > 0 && cuts.every((c) => (names[c] ?? "").trim());
  return (
    <Shell title="Split this page" hint="Click between two blocks to place a cut, then name the page that starts there. The first part stays here with a Continued in list.">
      <BlocksState q={q}>
        {(b) => {
          const rows = b.blocks.filter((x) => x.index >= b.first && x.text.trim());
          return (
            <ol className="flex max-h-[45vh] flex-col overflow-y-auto" aria-label="Page blocks">
              <li className="px-2 pb-1 text-xs text-muted-foreground">Stays on this page</li>
              {rows.map((blk, i) => {
                const cut = cuts.includes(blk.index);
                return (
                  <li key={blk.index} className="flex flex-col">
                    {i > 0 && (
                      <div className={cn("flex items-center gap-2", cut ? "py-1" : "")}>
                        <button
                          type="button"
                          aria-label={cut ? `Remove the cut before block ${blk.index}` : `Cut before block ${blk.index}`}
                          aria-pressed={cut}
                          onClick={() => setCuts((c) => toggleCut(c, blk.index))}
                          className="group flex h-5 w-full items-center gap-2 text-xs text-muted-foreground"
                        >
                          <span className={cn("h-px flex-1", cut ? "bg-foreground" : "bg-border group-hover:bg-foreground/60")} />
                          <span className={cn(cut ? "text-foreground" : "hidden group-hover:inline group-focus-visible:inline")}>{cut ? "Remove cut" : "Cut here"}</span>
                          <span className={cn("h-px flex-1", cut ? "bg-foreground" : "bg-border group-hover:bg-foreground/60", !cut && "hidden group-hover:block group-focus-visible:block")} />
                        </button>
                      </div>
                    )}
                    {cut && (
                      <Input
                        aria-label={`Title of the page starting at block ${blk.index}`}
                        placeholder="Name this new page"
                        value={names[blk.index] ?? ""}
                        onChange={(e) => setNames((n) => ({ ...n, [blk.index]: e.target.value }))}
                        className="mb-1"
                      />
                    )}
                    <p className={cn(BLOCK, kindClass(blk.kind))}>{clip(blk.text, 140)}</p>
                  </li>
                );
              })}
            </ol>
          );
        }}
      </BlocksState>
      <Footer
        error={make.isError ? errText(make.error) : null}
        pending={make.isPending}
        ready={ready}
        label={cuts.length > 1 ? `Create proposal (${cuts.length + 1} pages)` : "Create proposal"}
        onCreate={() => make.mutate()}
        done={make.data && <Done result={make.data} />}
      />
    </Shell>
  );
}

// -- extract -----------------------------------------------------------------------------------------------------------------
function ExtractBody({ slug }: { slug: string }) {
  const ds = useDataSource();
  const qc = useQueryClient();
  const q = useBlocks(slug);
  const [range, setRange] = useState<Range | null>(null);
  const [title, setTitle] = useState("");
  const make = useMutation({
    mutationFn: () => ds.restructureExtract({ slug, from_at: range!.from, to_at: range!.to, title: title.trim() }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["proposals"] }),
  });
  return (
    <Shell title="Extract to a new page" hint="Click the first and then the last block to move. A link to the new page is left in their place.">
      <BlocksState q={q}>
        {(b) => (
          <ol className="flex max-h-[40vh] flex-col overflow-y-auto" aria-label="Page blocks">
            {b.blocks
              .filter((x) => x.index >= b.first && x.text.trim())
              .map((blk) => {
                const on = !!range && blk.index >= range.from && blk.index <= range.to;
                return (
                  <li key={blk.index}>
                    <button
                      type="button"
                      aria-pressed={on}
                      aria-label={`Block ${blk.index}`}
                      onClick={() => setRange((r) => pickRange(r, blk.index))}
                      className={cn(BLOCK, "w-full text-left transition-colors hover:bg-muted", on ? "bg-muted text-foreground" : kindClass(blk.kind))}
                    >
                      {clip(blk.text, 140)}
                    </button>
                  </li>
                );
              })}
          </ol>
        )}
      </BlocksState>
      <p className="min-h-5 text-xs text-muted-foreground">
        {range ? (range.open ? `Block ${range.from} chosen; click the last block.` : `Blocks ${range.from} to ${range.to} will move.`) : "No blocks chosen yet."}
      </p>
      <Input aria-label="Title of the new page" placeholder="Title of the new page" value={title} onChange={(e) => setTitle(e.target.value)} />
      <Footer
        error={make.isError ? errText(make.error) : null}
        pending={make.isPending}
        ready={!!range && !range.open && !!title.trim()}
        label="Create proposal"
        onCreate={() => make.mutate()}
        done={make.data && <Done result={make.data} />}
      />
    </Shell>
  );
}
