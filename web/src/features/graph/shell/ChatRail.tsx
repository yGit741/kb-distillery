import { FileText, Network, PanelRightOpen } from "lucide-react";
import { useChatFull } from "./chatFullStore";

/**
 * The right pane folded to a 44px rail (flag `chat-full`): open, graph, pages and the colour dots, each one click
 * back to the pane, so the chat can take the whole width.
 */
export function ChatRail({ colors }: { colors: readonly string[] }) {
  const unfold = () => useChatFull.getState().setFolded(false);
  const btn = "grid size-8 place-items-center rounded-lg text-muted-foreground hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";
  return (
    <aside aria-label="Graph and pages, folded" data-testid="chat-rail" className="pointer-events-auto absolute inset-y-0 right-0 z-40 flex w-11 flex-col items-center gap-1 border-l bg-card py-3">
      <button type="button" className={btn} aria-label="Open the graph pane" title="Open the graph pane" onClick={unfold}>
        <PanelRightOpen aria-hidden className="size-4" strokeWidth={1.6} />
      </button>
      <button type="button" className={btn} aria-label="Graph" title="Graph" onClick={unfold}>
        <Network aria-hidden className="size-4" strokeWidth={1.6} />
      </button>
      <button type="button" className={btn} aria-label="Pages" title="Pages" onClick={unfold}>
        <FileText aria-hidden className="size-4" strokeWidth={1.6} />
      </button>
      {colors.length > 0 && (
        <button type="button" className={`${btn} mt-2 h-auto flex-col gap-1.5 py-2`} aria-label="Legend" title="Legend" onClick={unfold}>
          {colors.map((c) => (
            <span key={c} aria-hidden className="size-2 rounded-full" style={{ background: c }} />
          ))}
        </button>
      )}
    </aside>
  );
}
