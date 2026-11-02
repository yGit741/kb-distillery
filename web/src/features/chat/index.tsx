import { ErrorBoundary } from "@/components/states";
import { ChatScreen } from "./ChatScreen";

export default function Screen() {
  return (
    <ErrorBoundary label="Chat">
      <ChatScreen />
    </ErrorBoundary>
  );
}
