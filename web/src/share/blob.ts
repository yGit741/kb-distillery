import type { CitationGraph, LifecycleSnapshot, PageDetail, PageIndex, PinnedView, RawCard, ReadyView } from "@/api/types";
import type { GraphSnapshot } from "@/api/types";

/** What the share builder (backend kb_distillery.publish.site.build) bakes into `<script id="kb-data">`. */
export interface ShareMeta {
  kb_version: string;
  content_sha: string;
  viewer_sha: string;
  profile: string;
  built_at: string;
}

export interface ShareBlob {
  graph: GraphSnapshot;
  index: PageIndex;
  pages: Record<string, PageDetail>;
  /** Private profile only (the first-parent history as of the content commit). */
  lifecycle?: LifecycleSnapshot;
  /** Only when the builder had a citation graph; the legacy build never had one. */
  citations?: CitationGraph;
  meta?: ShareMeta;
  /** Home pipeline cards per source slug (kb_distillery.services.raw_card.bake_cards); public: the privacy column applied. */
  rawCards?: Record<string, RawCard>;
  /** Flag graph-intent, read-only: the kit's ready views; the pinned views and favorite pages (private profile only). */
  views?: PinnedView[];
  readyViews?: ReadyView[];
  favorites?: string[];
  /** Home cards and the tour id from share.toml `[home]` (kb_distillery.publish.site.home); `view` = the graph view a
   *  snapshot built with `share snapshot … --view <id>` opens on when the URL has no `?view=`. */
  home?: { cards?: unknown[]; tour?: string | null; view?: string | null };
}

/** Parse the baked blob out of the document; null when the page has none (plain app, tests). */
export function readBlob(doc: Document = document): ShareBlob | null {
  const el = doc.getElementById("kb-data");
  if (!el?.textContent) return null;
  return JSON.parse(el.textContent) as ShareBlob;
}

declare global {
  // eslint-disable-next-line no-var
  var KB_EMBEDDED: ShareBlob | undefined;
}
