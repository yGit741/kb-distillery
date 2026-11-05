import { Navigate, useParams, useSearch } from "@tanstack/react-router";
import { ErrorBoundary } from "@/components/states";
import { useFlag } from "@/flags/useFlag";
import type { ChatSearch } from "@/routes/search";
import { ChatScreen } from "./ChatScreen";

/**
 * Flag `chat-full`: there is no separate chat screen. `/chat` and `/chat/<id>` (the links, the nav and the palette
 * keep working) open the graph with the full chat; the old layout below stays while the flag is off.
 */
function ToFullChat() {
  const { id } = useParams({ strict: false }) as { id?: string };
  const search = useSearch({ strict: false }) as ChatSearch;
  return (
    <Navigate
      to={"/graph" as "/"}
      replace
      search={{ chat: id ?? search.session ?? "open", ...(search.scope ? { scope: search.scope } : {}), ...(search.q ? { ask: search.q } : {}) } as never}
    />
  );
}

export default function Screen() {
  // the full chat is the spark panel grown, so it needs spark-chat and the calm shell too
  const [chatFull, sparkChat, shell] = [useFlag("chat-full"), useFlag("spark-chat"), useFlag("graph-shell")];
  const full = chatFull && sparkChat && shell;
  const { id } = useParams({ strict: false }) as { id?: string };
  if (full) return <ToFullChat />;
  // /chat/<id> exists only for the full chat; without it the address is as unknown as any other
  if (id) return <p>Not Found</p>;
  return (
    <ErrorBoundary label="Chat">
      <ChatScreen />
    </ErrorBoundary>
  );
}
