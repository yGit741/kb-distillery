import { ErrorBoundary } from "@/components/states";
import { ChatScreen } from "./ChatScreen";

export const ported = true;

export default function Screen() {
  return (
    <ErrorBoundary label="Chat">
      <ChatScreen />
    </ErrorBoundary>
  );
}
