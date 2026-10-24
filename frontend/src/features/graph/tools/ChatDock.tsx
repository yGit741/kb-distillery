import { useSearch } from "@tanstack/react-router";
import { Maximize2, MessageSquare, Minimize2, X } from "lucide-react";
import { create } from "zustand";
import { ErrorBoundary } from "@/components/states";
import { Button } from "@/components/ui/button";
import { ChatScreen } from "@/features/chat/ChatScreen";
import { cn } from "@/lib/utils";
import type { SearchById } from "@/routes/search";

interface ChatDockState {
  open: boolean;
  wide: boolean;
  /** The last question handed in by "/" in the finder; ChatScreen prefills it. */
  question: string;
  ask: (question: string) => void;
  set: (s: Partial<Pick<ChatDockState, "open" | "wide">>) => void;
}

/** The research chat docked on the right of the graph (it replaces the Chat tab). */
export const useChatDock = create<ChatDockState>((set) => ({
  open: false,
  wide: false,
  question: "",
  ask: (question) => set({ open: true, question }),
  set: (s) => set(s),
}));

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

/** The dock itself: the full chat screen in a right-hand panel, widened on demand. */
export function ChatDock() {
  const open = useChatDock((s) => s.open);
  return open ? <OpenDock /> : null;
}

function OpenDock() {
  const { wide, question, set } = useChatDock();
  const search = useSearch({ strict: false }) as SearchById["graph"];
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
          <ChatScreen question={question} scope={search.scope} />
        </ErrorBoundary>
      </div>
    </aside>
  );
}
