import { useMemo } from "react";
import { cn } from "@/lib/utils";
import { NodeSwatch } from "../encoding/NodeMarkSvg";
import { swatchColor } from "../nodeColor";
import type { ColorBy } from "../style";
import { SideReader } from "../SideReader";
import type { GNode } from "../types";
import { useChatFull } from "./chatFullStore";

/**
 * The mini explorer under the graph in the full chat (flag `chat-full`): the pages the chat cited and the page open
 * in the reader (the graph's reader slot, so a click on a node's reader and a click here show the same page).
 */
export function ChatExplorer({
  byId,
  colorBy,
  slug,
  onPick,
  pageHref,
  onClose,
}: {
  byId: ReadonlyMap<string, GNode>;
  colorBy: ColorBy;
  /** the page open in the reader, if any */
  slug: string | null;
  onPick: (slug: string) => void;
  pageHref: (slug: string) => string;
  onClose: () => void;
}) {
  const cited = useChatFull((s) => s.cited);
  const rows = useMemo(() => cited.map((slug) => ({ slug, node: byId.get(slug) })), [cited, byId]);
  const pages = rows.filter((r) => r.node?.layer !== "source");
  const sources = rows.filter((r) => r.node?.layer === "source");
  const shown = slug ?? rows[0]?.slug ?? null;
  const item = (r: { slug: string; node?: GNode }) => (
    <li key={r.slug}>
      <button
        type="button"
        onClick={() => onPick(r.slug)}
        aria-current={r.slug === shown ? "true" : undefined}
        title={r.node?.title || r.slug}
        className={cn(
          "flex w-full items-center gap-2 px-3 py-1.5 text-left text-[13px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring",
          r.slug === shown ? "bg-secondary" : "hover:bg-secondary/60",
        )}
      >
        {r.node && <NodeSwatch type={r.node.type} color={swatchColor(r.node, colorBy)} className="size-3.5" />}
        <span className="min-w-0 flex-1 truncate">{r.node?.title || r.slug}</span>
      </button>
    </li>
  );
  const group = (label: string, list: typeof rows) =>
    list.length > 0 && (
      <section aria-label={label}>
        <h3 className="px-3 pb-1 pt-3 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</h3>
        <ul>{list.map(item)}</ul>
      </section>
    );
  return (
    <div data-testid="chat-explorer" className="pointer-events-auto flex size-full min-w-0 border-t bg-card text-card-foreground">
      <div className="w-[200px] shrink-0 overflow-y-auto border-r">
        {rows.length === 0 && <p className="px-3 pt-3 text-xs text-muted-foreground">Pages the chat cites show up here.</p>}
        {group("Cited pages", pages)}
        {group("Sources", sources)}
      </div>
      <div className="min-w-0 flex-1">
        {shown ? (
          <SideReader inline slug={shown} title={byId.get(shown)?.title || shown} pageHref={pageHref(shown)} onClose={onClose} />
        ) : (
          <p className="p-4 text-sm text-muted-foreground">Click a page in the list, or a node on the graph and open it, to read it here.</p>
        )}
      </div>
    </div>
  );
}
