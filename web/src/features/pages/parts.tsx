import { Link } from "@tanstack/react-router";
import { createContext, useContext, type ReactNode } from "react";
import type { PageCard } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { NodeMarkSvg } from "@/features/graph/encoding";
import { depthColor } from "@/theme/palette";
import { layerOf, type LinkGraph } from "./lib";

/** Router targets are registered as plain strings by the route registry, so cast once here. */
export const pageTo = (slug: string) => `/pages/${encodeURIComponent(slug)}` as "/";
export const PAGES_TO = "/pages" as "/";

/** The knowledge base the pages on screen come from when it is not the server's own (read-only), else undefined. */
export const PageKb = createContext<string | undefined>(undefined);
/** Link `search` that keeps a page link inside that knowledge base. */
export const usePageSearch = () => {
  const kb = useContext(PageKb);
  return (kb ? { kb } : {}) as never;
};

/**
 * A page's type as the graphs draw it: its mark (a concept's ring, a source's glyph), the same symbol as on every
 * graph; the type's name on hover.
 */
export function TypeDot({ type, className }: { type?: string | null; className?: string }) {
  return (
    <span aria-hidden title={type ?? undefined} className="inline-flex shrink-0 text-muted-foreground" data-type-mark={type ?? ""}>
      <NodeMarkSvg type={type ?? ""} className={cn("size-3.5", className)} />
    </span>
  );
}

/** A link to a page, or a muted label if the page does not exist (a wanted page). */
export function PageLink({ g, slug, label }: { g?: LinkGraph; slug: string; label?: string }) {
  const search = usePageSearch();
  if (g && !g.byId.has(slug)) {
    return (
      <span className="text-muted-foreground" title={`No page yet: ${slug}`}>
        {label ?? slug}
      </span>
    );
  }
  return (
    <Link to={pageTo(slug)} search={search} className="text-primary hover:underline">
      {label ?? (g ? (g.byId.get(slug)?.title ?? slug) : slug)}
    </Link>
  );
}

/** layer / type / depth (sources only) / status / year, in the palette's colours. */
export function FactBadges({ card }: { card: PageCard }) {
  const layer = layerOf(card.type);
  return (
    <div className="flex flex-wrap items-center gap-1.5" aria-label="Page facts">
      {layer && (
        <Link to={PAGES_TO} search={{ layer } as never} title="Browse this layer">
          <Badge variant="outline">{layer}</Badge>
        </Link>
      )}
      <Link to={PAGES_TO} search={{ type: card.type } as never} title="Browse this type">
        <Badge className="gap-1.5">
          <TypeDot type={card.type} />
          {card.type}
        </Badge>
      </Link>
      {layer === "source" && card.depth && (
        <Badge title="depth" style={{ boxShadow: `inset 0 0 0 1px ${depthColor(card.depth)}` }}>
          {card.depth}
        </Badge>
      )}
      {card.status && <Badge variant="outline">{card.status}</Badge>}
      {card.year ? <Badge variant="outline">{card.year}</Badge> : null}
    </div>
  );
}

export function Section({ title, hint, children }: { title: ReactNode; hint?: string; children: ReactNode }) {
  return (
    <section className="flex min-w-0 flex-col gap-2">
      <h2 className="text-base font-semibold">{title}</h2>
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      {children}
    </section>
  );
}

export function PageCardTile({ g, card }: { g: LinkGraph; card: PageCard }) {
  const meta = [card.year, card.depth || card.status, `${g.inn.get(card.id)?.size ?? 0}↘ ${g.out.get(card.id)?.size ?? 0}↗`]
    .filter(Boolean)
    .join(" · ");
  const search = usePageSearch();
  return (
    <Link
      to={pageTo(card.id)}
      search={search}
      className="flex min-w-0 flex-col gap-1 rounded-lg border bg-card p-3 text-sm hover:bg-accent"
    >
      <span className="flex items-center gap-2 font-medium">
        <TypeDot type={card.type} />
        <span className="min-w-0 break-words">{card.title}</span>
      </span>
      {card.preview && <span className="line-clamp-3 text-xs text-muted-foreground">{card.preview}</span>}
      <span className="text-xs text-muted-foreground">{meta}</span>
    </Link>
  );
}

export function Rows({ children }: { children: ReactNode }) {
  return <ul className="flex flex-col divide-y rounded-lg border bg-card text-sm">{children}</ul>;
}
export function Row({ card, right }: { card: PageCard; right?: ReactNode }) {
  const search = usePageSearch();
  return (
    <li className="flex min-w-0 items-center gap-2 px-3 py-1.5">
      <TypeDot type={card.type} />
      <Link to={pageTo(card.id)} search={search} className="min-w-0 flex-1 truncate text-primary hover:underline">
        {card.title}
      </Link>
      {right != null && <span className="shrink-0 text-xs text-muted-foreground">{right}</span>}
    </li>
  );
}

/** A collapsible card: the reader's side folds and the video view's description and comments. */
export function Fold({ title, count, children }: { title: string; count?: number; children: ReactNode }) {
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
