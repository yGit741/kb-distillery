import { useSearch } from "@tanstack/react-router";
import { Maximize2, MessageSquare, Minimize2, X } from "lucide-react";
import { lazy, Suspense } from "react";
import { ErrorBoundary, Loading } from "@/components/states";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { SearchById } from "@/routes/search";
import { useChatDock } from "./chatDockStore";

export { askAbout, useChatDock } from "./chatDockStore";

// The chat screen loads on first open, and never in a share build: the MODE test is replaced at build time,
// so a snapshot carries no chat code at all.
const ChatScreen =
  import.meta.env.MODE === "share" ? null : lazy(() => import("@/features/chat/ChatScreen").then((m) => ({ default: m.ChatScreen })));

/** The flyout body of the chat tool: one button, since the chat itself lives in the dock. */
export function ChatToolPanel() {
  const { open, set } = useChatDock();
  return (
    <div className="flex flex-col gap-2 text-sm">
      <p className="text-muted-foreground">Ask the research agent about the vault. In the search, type “/” and a question to send it straight here.</p>
      <Button size="sm" onClick={() => set({ open: !open })}>
        <MessageSquare aria-hidden /> {open ? "Close chat" : "Open chat"}
      </Button>
    </div>
  );
}

/** The dock itself: the full chat screen in a right-hand panel, widened on demand (replaces the Chat tab). */
export function ChatDock() {
  const open = useChatDock((s) => s.open);
  return open && ChatScreen ? <OpenDock /> : null;
}

function OpenDock() {
  const { wide, question, set } = useChatDock();
  const search = useSearch({ strict: false }) as SearchById["graph"];
  if (!ChatScreen) return null;
  return (
    <aside
      aria-label="Chat"
      className={cn(
        "pointer-events-auto absolute inset-y-0 right-0 z-40 flex flex-col border-l bg-background text-foreground shadow-[var(--shadow)]",
        wide ? "w-full" : "w-[min(46rem,100%)]",
      )}
    >
      <header className="flex items-center gap-2 border-b bg-card px-3 py-2">
        <MessageSquare aria-hidden className="size-4 text-muted-foreground" />
        <h2 className="min-w-0 flex-1 text-sm font-semibold">Ask the vault</h2>
        <Button variant="ghost" size="icon" className="size-8" aria-label={wide ? "Narrow chat" : "Widen chat"} onClick={() => set({ wide: !wide })}>
          {wide ? <Minimize2 aria-hidden /> : <Maximize2 aria-hidden />}
        </Button>
        <Button variant="ghost" size="icon" className="size-8" aria-label="Close chat" onClick={() => set({ open: false })}>
          <X aria-hidden />
        </Button>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        <ErrorBoundary label="Chat">
          <Suspense fallback={<Loading label="Loading chat" rows={3} />}>
            <ChatScreen question={question} scope={search.scope} />
          </Suspense>
        </ErrorBoundary>
      </div>
    </aside>
  );
}
