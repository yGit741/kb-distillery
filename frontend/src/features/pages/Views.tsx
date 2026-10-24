import { Link } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";
import { LAYER_TYPES } from "@/api/model";
import type { PageCard, PageIndex } from "@/api/types";
import { useApiQuery } from "@/lib/useApiQuery";
import { Empty, ErrorState, Loading } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import {
  agoLabel,
  filterCards,
  highlightParts,
  homeSections,
  mtimeOf,
  resolveInput,
  SORTS,
  sortCards,
  titleOf,
  type LinkGraph,
  type Sort,
} from "./lib";
import { PAGES_TO, PageCardTile, PageLink, Row, Rows, Section, TypeDot, pageTo } from "./parts";

const Grid = ({ cards, g }: { cards: PageCard[]; g: LinkGraph }) => (
  <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
    {cards.map((c) => (
      <PageCardTile key={c.id} g={g} card={c} />
    ))}
  </div>
);

export function HomeView({ g, index }: { g: LinkGraph; index: PageIndex }) {
  const h = homeSections(g);
  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold">Pages</h1>
        <p className="text-sm text-muted-foreground">
          {g.byId.size} pages · {index.links.length} links · {h.questions.length} open questions · {h.deep.length} read in depth
        </p>
        <div className="flex flex-col gap-1.5">
          {(Object.keys(LAYER_TYPES) as (keyof typeof LAYER_TYPES)[]).map((layer) => (
            <div key={layer} className="flex flex-wrap items-center gap-1.5">
              <Link to={PAGES_TO} search={{ layer } as never} className="w-24 text-xs font-medium text-muted-foreground hover:underline">
                {layer}
              </Link>
              {LAYER_TYPES[layer].filter((t) => h.counts.get(t)).map((t) => (
                <Link
                  key={t}
                  to={PAGES_TO}
                  search={{ type: t } as never}
                  className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs hover:bg-accent"
                >
                  <TypeDot type={t} />
                  {t} <b>{h.counts.get(t)}</b>
                </Link>
              ))}
            </div>
          ))}
        </div>
      </header>

      {h.topics.length > 0 && (
        <Section title="Start from a topic" hint="Each topic page is a map into one research direction.">
          <Grid g={g} cards={h.topics.slice(0, 9)} />
          {h.topics.length > 9 && (
            <Link to={PAGES_TO} search={{ type: "topic" } as never} className="text-sm text-primary hover:underline">
              All {h.topics.length} topics →
            </Link>
          )}
        </Section>
      )}
      {h.questions.length > 0 && (
        <Section title="Open questions" hint="The live threads: what the vault is trying to decide.">
          <Grid g={g} cards={h.questions.slice(0, 9)} />
        </Section>
      )}
      <div className="grid gap-6 md:grid-cols-2">
        <Section title="Read in depth" hint="Sources with a full or deep write-up, deepest first.">
          <Rows>
            {h.deep.slice(0, 12).map((p) => (
              <Row key={p.id} card={p} right={p.depth} />
            ))}
          </Rows>
        </Section>
        <Section title="Recently touched">
          <Rows>
            {h.recent.map((p) => (
              <Row key={p.id} card={p} right={agoLabel(mtimeOf(p))} />
            ))}
          </Rows>
        </Section>
        <Section title="Worth reading next" hint="Heavily linked sources that are still thin notes.">
          {h.worthReading.length ? (
            <Rows>
              {h.worthReading.map((p) => (
                <Row key={p.id} card={p} right={`${g.inn.get(p.id)?.size ?? 0} links · ${p.words}w`} />
              ))}
            </Rows>
          ) : (
            <Empty>None: nice.</Empty>
          )}
        </Section>
        <Section title={`Wanted pages (${index.wanted_total})`} hint="Linked to, but not written yet.">
          <ul className="flex flex-col divide-y rounded-lg border bg-card text-sm">
            {index.wanted.slice(0, 10).map((w) => (
              <li key={w.id} className="flex min-w-0 flex-col px-3 py-1.5">
                <span className="truncate text-muted-foreground">{w.id}</span>
                <span className="min-w-0 truncate text-xs text-muted-foreground">
                  {w.count}× from <PageLink g={g} slug={Array.isArray(w.from) ? String(w.from[0] ?? "") : ""} />
                </span>
              </li>
            ))}
          </ul>
        </Section>
      </div>
      {h.people.length > 0 && (
        <Section title="People">
          <div className="flex flex-wrap gap-1.5">
            {h.people.map((p) => (
              <Link key={p.id} to={pageTo(p.id)} className="rounded-full border px-2.5 py-1 text-xs hover:bg-accent">
                {p.title}
              </Link>
            ))}
          </div>
        </Section>
      )}
      <Section title={`Orphans (${h.orphans.length})`} hint="Nothing links here.">
        <Rows>
          {h.orphans.slice(0, 10).map((p) => (
            <Row key={p.id} card={p} right={p.type} />
          ))}
        </Rows>
      </Section>
    </div>
  );
}

export function BrowseView({ g, layer, type }: { g: LinkGraph; layer?: string; type?: string }) {
  const [sort, setSort] = useState<Sort>("links");
  const cards = sortCards(g, filterCards([...g.byId.values()], { layer, type }), sort);
  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-col gap-2">
        <h1 className="flex items-center gap-2 text-2xl font-semibold">
          {type && <TypeDot type={type} />}
          {type ?? layer} <span className="text-base font-normal text-muted-foreground">{cards.length}</span>
        </h1>
        <div className="flex flex-wrap items-center gap-1 text-sm" role="group" aria-label="Sort by">
          <span className="text-muted-foreground">sort:</span>
          {SORTS.map((s) => (
            <Button key={s} size="sm" variant={s === sort ? "secondary" : "ghost"} aria-pressed={s === sort} onClick={() => setSort(s)}>
              {s}
            </Button>
          ))}
        </div>
      </header>
      {cards.length ? <Grid g={g} cards={cards} /> : <Empty>No pages here.</Empty>}
    </div>
  );
}

function Marked({ text, query }: { text: string; query: string }) {
  return (
    <>
      {highlightParts(text, query).map((p, i) =>
        p.hit ? <mark key={i} className="rounded bg-warn/30 text-foreground">{p.text}</mark> : <span key={i}>{p.text}</span>,
      )}
    </>
  );
}

export function SearchView({ g, q }: { g: LinkGraph; q: string }) {
  const res = useApiQuery(["pages", "search", q], (ds) => ds.search(q, 40), { enabled: q.trim().length >= 2 });
  if (q.trim().length < 2) return <Empty>Type at least two characters.</Empty>;
  if (res.isPending) return <Loading label="Searching" rows={4} />;
  if (res.isError) return <ErrorState title="Search failed." error={res.error} onRetry={() => void res.refetch()} />;
  const { hits, total } = res.data;
  return (
    <div className="flex flex-col gap-3">
      <header>
        <h1 className="text-2xl font-semibold">“{q}”</h1>
        <p className="text-sm text-muted-foreground">
          {total} page{total === 1 ? "" : "s"}
          {total > hits.length ? ` · showing ${hits.length}` : ""}
        </p>
      </header>
      {hits.length === 0 ? (
        <Empty>No matches.</Empty>
      ) : (
        <ul className="flex flex-col divide-y rounded-lg border bg-card">
          {hits.map((h) => (
            <li key={h.id}>
              <Link to={pageTo(h.id)} className="flex min-w-0 flex-col gap-0.5 px-3 py-2 [overflow-wrap:anywhere] hover:bg-accent">
                <span className="flex flex-wrap items-center gap-2 font-medium">
                  <TypeDot type={h.type} />
                  <Marked text={h.title || titleOf(g, h.id)} query={q} />
                  <span className="text-xs font-normal text-muted-foreground">{h.type}</span>
                </span>
                <span className="text-sm text-muted-foreground">
                  <Marked text={h.snippet} query={q} />
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function PathView({ g, initialA = "", initialB = "" }: { g: LinkGraph; initialA?: string; initialB?: string }) {
  const [draft, setDraft] = useState({ a: initialA, b: initialB });
  const [ask, setAsk] = useState<{ a: string; b: string } | null>(initialA && initialB ? { a: initialA, b: initialB } : null);
  const res = useApiQuery(["pages", "path", ask?.a, ask?.b], (ds) => ds.findPath(ask!.a, ask!.b), {
    enabled: !!ask,
    retry: false,
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (draft.a.trim() && draft.b.trim())
      setAsk({ a: resolveInput(g, draft.a), b: resolveInput(g, draft.b) });
  };
  const names = [...g.byId.values()];
  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold">How are two pages connected?</h1>
        <p className="text-sm text-muted-foreground">Shortest chain of links in either direction, with the sentence behind each link.</p>
        <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <Input list="pages-all" aria-label="From page" placeholder="from page" value={draft.a} onChange={(e) => setDraft({ ...draft, a: e.target.value })} />
          <span aria-hidden className="hidden sm:inline">→</span>
          <Input list="pages-all" aria-label="To page" placeholder="to page" value={draft.b} onChange={(e) => setDraft({ ...draft, b: e.target.value })} />
          <Button type="submit">Find path</Button>
          <datalist id="pages-all">
            {names.map((p) => (
              <option key={p.id} value={p.id}>{p.title}</option>
            ))}
          </datalist>
        </form>
      </header>
      {!ask ? null : res.isPending ? (
        <Loading label="Finding path" rows={2} />
      ) : res.isError ? (
        <p role="alert" className="text-sm text-bad">One of those pages does not exist. Pick from the suggestions while typing.</p>
      ) : res.data.distance == null ? (
        <p className="text-sm">No chain of links connects these two pages; they sit in separate islands of the graph.</p>
      ) : res.data.distance === 0 ? (
        <p className="text-sm text-muted-foreground">Same page.</p>
      ) : (
        <div className="flex flex-col gap-4">
          <p className="text-sm text-muted-foreground">
            {res.data.distance} hop{res.data.distance > 1 ? "s" : ""} · {res.data.paths.length} shortest route{res.data.paths.length > 1 ? "s" : ""}
          </p>
          {res.data.paths.map((p, i) => (
            <Section key={i} title={`Route ${i + 1}`}>
              <ol className="flex flex-col gap-1 text-sm">
                <li className="flex items-center gap-2">
                  <TypeDot type={g.byId.get(p.nodes[0] ?? "")?.type} />
                  <PageLink g={g} slug={p.nodes[0] ?? ""} />
                </li>
                {p.hops.map((h, j) => {
                  const to = p.nodes[j + 1] ?? "";
                  return (
                    <li key={j} className="flex flex-col gap-1">
                      <span className={cn("ml-1 border-l-2 pl-3 text-xs text-muted-foreground")}>
                        {h.dir === "forward" ? "↓ links to" : "↑ is linked from"}
                        {h.context && <span className="block">{h.context}</span>}
                      </span>
                      <span className="flex items-center gap-2">
                        <TypeDot type={g.byId.get(to)?.type} />
                        <PageLink g={g} slug={to} />
                      </span>
                    </li>
                  );
                })}
              </ol>
            </Section>
          ))}
        </div>
      )}
    </div>
  );
}
