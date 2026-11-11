import { SideReader } from "../SideReader";
import type { GNode } from "../types";

/**
 * The page viewer under the graph in the full chat (flag `chat-full`): the page open in the reader (the graph's reader
 * slot, so a click on a node and a click on a citation show the same page). The pages an answer cites are listed on
 * that answer (./CitesButton), not here.
 */
export function ChatExplorer({
  byId,
  slug,
  pageHref,
  onClose,
}: {
  byId: ReadonlyMap<string, GNode>;
  slug: string;
  pageHref: (slug: string) => string;
  onClose: () => void;
}) {
  return (
    <div data-testid="chat-explorer" className="pointer-events-auto size-full min-w-0 border-t bg-card text-card-foreground">
      <SideReader inline slug={slug} title={byId.get(slug)?.title || slug} pageHref={pageHref(slug)} onClose={onClose} />
    </div>
  );
}
