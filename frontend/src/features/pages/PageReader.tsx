import { Link } from "@tanstack/react-router";
import { Check, Copy, ExternalLink, Pin, PinOff } from "lucide-react";
import { useCallback, useMemo, useState, type ReactNode } from "react";
import type { PageDetail } from "@/api/types";
import { Markdown } from "@/components/Markdown";
import { Button } from "@/components/ui/button";
import { agoLabel, bareSlug, fmList, fmString, layerOf, mtimeOf, prepareMarkdown, titleOf, type LinkGraph } from "./lib";
import { MiniGraph } from "./MiniGraph";
import { PAGES_TO, FactBadges, PageLink, TypeDot } from "./parts";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

function Fold({ title, count, children }: { title: string; count?: number; children: ReactNode }) {
  return (
    <details className="group rounded-lg border bg-card">
      <summary className="flex cursor-pointer items-center gap-2 px-3 py-2 text-sm font-medium marker:content-none">
        <span aria-hidden className="text-muted-foreground transition-transform group-open:rotate-90">›</span>
        {title}
        {count != null && <span className="text-xs font-normal text-muted-foreground">{count}</span>}
      </summary>
      <div className="border-t px-3 py-2 text-sm">{children}</div>
    </details>
  );
}

function PageList({ g, items, empty }: { g: LinkGraph; items: { id: string; note?: ReactNode }[]; empty: string }) {
  if (!items.length) return <p className="text-muted-foreground">{empty}</p>;
  return (
    <ul className="flex flex-col gap-1.5">
      {items.map((it) => (
        <li key={it.id} className="flex min-w-0 flex-col">
          <span className="flex items-center gap-2">
            <TypeDot type={g.byId.get(it.id)?.type} />
            <PageLink g={g} slug={it.id} />
          </span>
          {it.note && <span className="pl-[18px] text-xs text-muted-foreground">{it.note}</span>}
        </li>
      ))}
    </ul>
  );
}

function RawFile({ path }: { path: string }) {
  const [copied, setCopied] = useState(false);
  const copy = useCallback(() => {
    void navigator.clipboard?.writeText(path).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }, [path]);
  return (
    <span className="inline-flex max-w-full items-center gap-1">
      <Link to={"/pipeline" as "/"} search={{ q: path } as never} className="min-w-0 truncate text-primary hover:underline" title="Open in the pipeline">
        <code className="text-xs">{path}</code>
      </Link>
      <button type="button" onClick={copy} className="rounded p-1 text-muted-foreground hover:bg-accent" aria-label="Copy raw path">
        {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
      </button>
    </span>
  );
}

export interface PageReaderProps {
  g: LinkGraph;
  detail: PageDetail;
  embed: boolean;
  pinned: boolean;
  onTogglePin: () => void;
  onConnect: () => void;
}

export function PageReader({ g, detail, embed, pinned, onTogglePin, onConnect }: PageReaderProps) {
  const { card, frontmatter: fm } = detail;
  const layer = layerOf(card.type);
  const resolveSlug = useCallback((raw: string) => (g.byId.has(bareSlug(raw)) ? bareSlug(raw) : null), [g]);
  const markdown = useMemo(() => prepareMarkdown(detail.markdown, (s) => g.byId.get(s)?.title), [detail.markdown, g]);

  const authors = fmList(fm, "authors");
  const url = fmString(fm, "url");
  const scholar = fmString(fm, "scholar");
  const raw = fmString(fm, "raw");
  const book = fmString(fm, "book");
  const topLink = embed ? { target: "_top" } : {};
  const sources = useMemo(
    () =>
      layer === "source"
        ? []
        : [...new Set([...(g.out.get(card.id) ?? []), ...(g.inn.get(card.id) ?? [])])]
            .filter((id) => layerOf(g.byId.get(id)?.type) === "source")
            .sort(),
    [g, card.id, layer],
  );

  return (
    <div className="grid min-w-0 gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
      <article className="flex min-w-0 flex-col gap-4">
        <header className="flex flex-col gap-2">
          <h1 className="text-2xl font-semibold leading-tight">{card.title}</h1>
          <FactBadges card={card} />
          {(card.areas.length > 0 || book) && (
            <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
              {book && layer === "source" && (
                <span>
                  in <PageLink g={g} slug={book} />
                  {fmString(fm, "section_pages") && ` · pp. ${fmString(fm, "section_pages").replace("-", "–")}`}
                </span>
              )}
              {card.areas.map((a) => (
                <span key={a} className="text-muted-foreground">
                  #{g.byId.has(`theme-${a}`) ? <PageLink g={g} slug={`theme-${a}`} label={a} /> : a}
                </span>
              ))}
            </p>
          )}
          {(authors.length > 0 || url || scholar || raw) && (
            <p className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
              {authors.length > 0 && <span>{authors.join(", ")}</span>}
              {/^https?:/i.test(url) && (
                <a className="inline-flex items-center gap-1 text-primary hover:underline" href={url} target="_blank" rel="noopener noreferrer">
                  source <ExternalLink className="size-3" aria-hidden />
                </a>
              )}
              {/^https?:/i.test(scholar) && (
                <a className="inline-flex items-center gap-1 text-primary hover:underline" href={scholar} target="_blank" rel="noopener noreferrer">
                  scholar <ExternalLink className="size-3" aria-hidden />
                </a>
              )}
              {raw && raw !== "none" && <RawFile path={raw} />}
            </p>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" size="sm" onClick={onTogglePin} aria-pressed={pinned}>
              {pinned ? <PinOff /> : <Pin />} {pinned ? "Unpin" : "Pin"}
            </Button>
            <Button variant="outline" size="sm" asChild>
              <a href={`${BASE}/graph?focus=${encodeURIComponent(card.id)}`} {...topLink}>Show in graph</a>
            </Button>
            {!embed && (
              <Button variant="outline" size="sm" onClick={onConnect}>
                Connect to…
              </Button>
            )}
            <Button variant="ghost" size="sm" asChild>
              <a href={`obsidian://open?file=${encodeURIComponent(detail.path)}`}>Open in Obsidian</a>
            </Button>
            <span className="text-xs text-muted-foreground">
              {card.words} words{mtimeOf(card) ? ` · edited ${agoLabel(mtimeOf(card))}` : ""}
            </span>
          </div>
        </header>

        <Markdown resolveSlug={resolveSlug}>{markdown}</Markdown>

        {detail.broken.length > 0 && (
          <p className="rounded-lg border border-warn/40 bg-warn/10 p-3 text-sm">
            <b>{detail.broken.length} wanted link{detail.broken.length > 1 ? "s" : ""}:</b>{" "}
            {detail.broken.map((b) => (
              <span key={b} className="mr-2 text-muted-foreground">{b}</span>
            ))}
          </p>
        )}
      </article>

      <aside className="flex min-w-0 flex-col gap-3" aria-label="Neighbourhood">
        <div className="rounded-lg border bg-card p-3">
          <h2 className="mb-2 text-sm font-medium">
            Neighbourhood{" "}
            <span className="text-xs font-normal text-muted-foreground">
              {g.inn.get(card.id)?.size ?? 0}↘ {g.out.get(card.id)?.size ?? 0}↗
            </span>
          </h2>
          <MiniGraph g={g} slug={card.id} />
        </div>
        {sources.length > 0 && (
          <Fold title="Sources" count={sources.length}>
            <PageList g={g} items={sources.map((id) => ({ id }))} empty="" />
          </Fold>
        )}
        <Fold title="Linked from" count={detail.backlinks.length}>
          <PageList g={g} items={detail.backlinks.map((b) => ({ id: b.id, note: b.context }))} empty="Nothing links here yet." />
        </Fold>
        <Fold title="Links to" count={detail.outbound.length}>
          <PageList g={g} items={detail.outbound.map((id) => ({ id }))} empty="No outgoing links." />
        </Fold>
        <Fold title="Related but unlinked" count={detail.suggested.length}>
          <PageList
            g={g}
            items={detail.suggested.map((s) => ({
              id: s.id,
              note: (
                <>
                  {s.shared} shared neighbours via{" "}
                  {s.via.map((v, i) => (
                    <span key={v}>{i > 0 && ", "}<PageLink g={g} slug={v} /></span>
                  ))}
                </>
              ),
            }))}
            empty="No strong candidates."
          />
        </Fold>
      </aside>
    </div>
  );
}

export const noPage = (g: LinkGraph | undefined, slug: string): ReactNode => (
  <div className="flex flex-col gap-2 py-6">
    <h1 className="text-xl font-semibold">No page “{g ? titleOf(g, slug) : slug}”</h1>
    <p className="text-sm text-muted-foreground">It may be a wanted page: linked to but not written yet.</p>
    <Link to={PAGES_TO} className="text-primary hover:underline">Back to Pages</Link>
  </div>
);
