import { useNavigate, useParams, useSearch } from "@tanstack/react-router";
import { Link } from "@tanstack/react-router";
import { Dices, Home, Route as RouteIcon } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "@/api";
import { Empty, ErrorState, Loading } from "@/components/states";
import { Button } from "@/components/ui/button";
import { useEmbed } from "@/app/embed";
import { useApiQuery } from "@/lib/useApiQuery";
import type { PagesSearch } from "@/routes/search";
import { cn } from "@/lib/utils";
import {
  buildGraph,
  loadList,
  parseLegacyHash,
  PINS_KEY,
  saveList,
  TRAIL_KEY,
  withPinToggled,
  withTrail,
  type LinkGraph,
} from "./lib";
import { noPage, PageReader } from "./PageReader";
import { PAGES_TO, TypeDot, pageTo } from "./parts";
import { SearchBox } from "./SearchBox";
import { BrowseView, HomeView, PathView, SearchView } from "./Views";

export const ported = true;

const isTyping = (t: EventTarget | null) =>
  t instanceof HTMLElement && (t.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(t.tagName));

function Chips({ title, slugs, g, current }: { title: string; slugs: string[]; g: LinkGraph; current?: string }) {
  if (!slugs.length) return null;
  return (
    <div className="flex items-center gap-1.5 overflow-x-auto pb-1 text-xs [scrollbar-width:thin]" aria-label={title} role="list">
      <span className="shrink-0 font-medium text-muted-foreground">{title}</span>
      {slugs.map((s) => (
        <Link
          key={s}
          role="listitem"
          to={pageTo(s)}
          className={cn(
            "inline-flex max-w-48 shrink-0 items-center gap-1.5 rounded-full border px-2 py-0.5 hover:bg-accent",
            s === current && "border-primary text-primary",
          )}
        >
          <TypeDot type={g.byId.get(s)?.type} />
          <span className="truncate">{g.byId.get(s)?.title ?? s}</span>
        </Link>
      ))}
    </div>
  );
}

export default function PagesScreen() {
  const embed = useEmbed();
  const navigate = useNavigate();
  const { slug } = useParams({ strict: false }) as { slug?: string };
  const search = useSearch({ strict: false }) as PagesSearch;
  const searchRef = useRef<HTMLInputElement>(null);

  // The finder is open when the URL carries a/b (shareable result) or the user opened it empty.
  const [openPath, setPath] = useState<{ a: string; b: string } | null>(null);
  const path = search.a || search.b ? { a: search.a ?? "", b: search.b ?? "" } : openPath;
  const askPath = useCallback(
    (a: string, b: string) =>
      void navigate({
        to: slug ? pageTo(slug) : PAGES_TO,
        search: { ...(embed ? { embed: "1" } : {}), a, b } as never,
        replace: true,
      }),
    [navigate, slug, embed],
  );
  const closePath = useCallback(() => {
    setPath(null);
    if (search.a || search.b)
      void navigate({ to: slug ? pageTo(slug) : PAGES_TO, search: (embed ? { embed: "1" } : {}) as never, replace: true });
  }, [navigate, slug, embed, search.a, search.b]);
  const [pins, setPins] = useState<string[]>(() => loadList(PINS_KEY));
  const [trail, setTrail] = useState<string[]>(() => loadList(TRAIL_KEY));

  const index = useApiQuery(["pages", "index"], (ds) => ds.listPages(), { staleTime: 60_000 });
  const g = useMemo(() => (index.data ? buildGraph(index.data) : undefined), [index.data]);
  const detail = useApiQuery(["pages", "page", slug], (ds) => ds.getPage(slug!), { enabled: !!slug, retry: false });

  // old `#/p/slug`, `#/search/q`, `#/browse/type`, `#/path/a/b` links
  useEffect(() => {
    const target = parseLegacyHash(window.location.hash);
    if (!target) return;
    if (target.kind === "page") void navigate({ to: pageTo(target.slug), replace: true });
    else if (target.kind === "search") void navigate({ to: PAGES_TO, search: { q: target.q } as never, replace: true });
    else if (target.kind === "browse") void navigate({ to: PAGES_TO, search: { type: target.type } as never, replace: true });
    else {
      void navigate({ to: PAGES_TO, search: { a: target.a ?? "", b: target.b ?? "" } as never, replace: true });
    }
  }, [navigate]);

  // leaving the view closes the path finder
  const viewKey = `${slug ?? ""}|${search.q ?? ""}|${search.type ?? ""}|${search.layer ?? ""}`;
  const firstKey = useRef(viewKey);
  useEffect(() => {
    if (firstKey.current !== viewKey) {
      firstKey.current = viewKey;
      setPath(null);
    }
  }, [viewKey]);

  const detailOk = detail.data && slug === detail.data.card.id;
  useEffect(() => {
    if (!detailOk || !slug) return;
    setTrail((t) => {
      const next = withTrail(t, slug);
      saveList(TRAIL_KEY, next);
      return next;
    });
    document.title = `${detail.data.card.title} - Pages`;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detailOk, slug]);

  const togglePin = useCallback(() => {
    if (!slug) return;
    setPins((p) => {
      const next = withPinToggled(p, slug);
      saveList(PINS_KEY, next);
      return next;
    });
  }, [slug]);

  const surprise = useCallback(() => {
    if (!g) return;
    const pool = [...g.byId.values()].filter((p) => p.words > 150 && p.type !== "ai-chat" && p.type !== "mail");
    const p = pool[Math.floor(Math.random() * pool.length)];
    if (p) void navigate({ to: pageTo(p.id) });
  }, [g, navigate]);

  useEffect(() => {
    if (embed) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || isTyping(e.target)) return;
      if (e.key === "/") {
        e.preventDefault();
        searchRef.current?.focus();
        searchRef.current?.select();
      } else if (e.key === "r") surprise();
      else if (e.key === "h") void navigate({ to: PAGES_TO });
      else if (e.key === "p") togglePin();
      else if (e.key === "g" && slug) window.location.assign(`${import.meta.env.BASE_URL}graph?focus=${encodeURIComponent(slug)}`);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [embed, surprise, togglePin, navigate, slug]);

  let body;
  if (index.isPending) body = <Loading label="Loading pages" rows={4} />;
  else if (index.isError || !g || !index.data)
    body = <ErrorState title="Could not load the page index." error={index.error} onRetry={() => void index.refetch()} />;
  else if (path) body = <PathView key={`${path.a}|${path.b}`} g={g} initialA={path.a} initialB={path.b} onAsk={askPath} />;
  else if (slug) {
    if (detail.isPending) body = <Loading label="Loading page" rows={5} />;
    else if (detail.isError)
      body =
        detail.error instanceof ApiError && detail.error.status === 404 ? (
          noPage(g, slug)
        ) : (
          <ErrorState title="Could not load this page." error={detail.error} onRetry={() => void detail.refetch()} />
        );
    else
      body = (
        <PageReader
          g={g}
          detail={detail.data}
          embed={embed}
          pinned={pins.includes(slug)}
          onTogglePin={togglePin}
          onConnect={() => setPath({ a: slug, b: "" })}
        />
      );
  } else if (search.q) body = <SearchView g={g} q={search.q} />;
  else if (search.type || search.layer) body = <BrowseView g={g} type={search.type} layer={search.layer} />;
  else body = <HomeView g={g} index={index.data} />;

  const content = (
    <div className="flex min-w-0 flex-col gap-4">
      {!embed && (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <SearchBox ref={searchRef} g={g} initial={search.q} key={search.q ?? ""} />
            <Button variant="outline" size="icon" asChild title="Pages home (h)">
              <Link to={PAGES_TO} aria-label="Pages home">
                <Home />
              </Link>
            </Button>
            <Button variant="outline" size="icon" onClick={surprise} disabled={!g} title="Random page (r)" aria-label="Random page">
              <Dices />
            </Button>
            <Button variant={path ? "secondary" : "outline"} size="icon" onClick={() => (path ? closePath() : setPath({ a: slug ?? "", b: "" }))} title="Connect two pages" aria-label="Connect two pages" aria-pressed={!!path}>
              <RouteIcon />
            </Button>
          </div>
          {g && <Chips title="Pinned" slugs={pins.filter((s) => g.byId.has(s))} g={g} current={slug} />}
          {g && <Chips title="Trail" slugs={trail.filter((s) => g.byId.has(s))} g={g} current={slug} />}
        </div>
      )}
      {body}
    </div>
  );

  if (!embed) return content;
  return (
    <div className="fixed inset-0 z-50 overflow-auto bg-background px-4 py-4" data-embed="true">
      {slug || index.isError ? content : <Empty>Pick a page.</Empty>}
    </div>
  );
}
