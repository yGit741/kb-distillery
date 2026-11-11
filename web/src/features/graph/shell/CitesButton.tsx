import { useEffect, useRef, useState } from "react";
import type { ChatMessage } from "@/features/chat/thread";
import { cn } from "@/lib/utils";
import { useGraphUi } from "../store";
import { useChatFull } from "./chatFullStore";
import { citedSlugs } from "./cites";
import { useThinking } from "./thinkingStore";

/**
 * The pages one answer cites, behind a quiet "N sources" control in its footer. The list keeps the answer's own order,
 * so row 3 is citation [3]. A click opens the page in the reader (the viewer under the graph in the full chat) and the
 * list stays open to walk several; hover rings the page on the graph; a double click hands it to the composer as @page.
 */
export function CitesButton({ message }: { message: ChatMessage }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const pages = useChatFull((s) => s.pages);
  const slugs = message.role === "assistant" ? citedSlugs(message.content) : [];

  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => {
      if (!box.current?.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("pointerdown", away);
    return () => window.removeEventListener("pointerdown", away);
  }, [open]);
  // a ring left on the graph by a hovered row goes when the list closes (not on mount: a new answer's button must not
  // clear a ring that replay or the thinking view holds)
  const wasOpen = useRef(false);
  useEffect(() => {
    if (wasOpen.current && !open) useThinking.getState().setHot(null);
    wasOpen.current = open;
  }, [open]);

  if (!slugs.length) return null;
  const title = (slug: string) => pages.find((p) => p.id === slug)?.title || slug;
  return (
    <div ref={box} className="relative">
      <button
        type="button"
        aria-expanded={open}
        aria-haspopup="true"
        data-testid="cites-button"
        className="rounded-md px-1.5 py-0.5 text-xs text-muted-foreground hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        onClick={() => setOpen((o) => !o)}
      >
        {slugs.length} source{slugs.length === 1 ? "" : "s"}
      </button>
      {open && (
        <div
          role="dialog"
          aria-label="Sources this answer cites"
          data-testid="cites-list"
          className="absolute bottom-full left-0 z-50 mb-1 max-h-72 w-72 overflow-y-auto rounded-lg border bg-card py-1 text-card-foreground shadow-[var(--shadow)]"
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              e.stopPropagation(); // closes the list, not the panel
              setOpen(false);
            }
          }}
        >
          <ol>
            {slugs.map((slug, n) => (
              <li key={slug}>
                <button
                  type="button"
                  title={title(slug)}
                  className={cn(
                    "flex w-full items-baseline gap-2 px-3 py-1.5 text-left text-[13px] hover:bg-secondary focus-visible:bg-secondary focus-visible:outline-none",
                    useGraphUi.getState().readerSlug === slug && "bg-secondary/60",
                  )}
                  onMouseEnter={() => useThinking.getState().setHot(slug)}
                  onMouseLeave={() => useThinking.getState().setHot(null)}
                  onClick={() => useGraphUi.setState({ readerSlug: slug })}
                  onDoubleClick={() => useChatFull.getState().mentionPage(slug, title(slug))}
                >
                  <span className="w-4 shrink-0 text-right text-xs tabular-nums text-muted-foreground">{n + 1}</span>
                  <span className="min-w-0 flex-1 truncate">{title(slug)}</span>
                </button>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
