import { useFlag } from "@/flags/useFlag";
import { useChatFull } from "./chatFullStore";
import { useSparkOpen } from "./SparkPanelHost";

/** The full chat is on show: flag `chat-full`, the panel open and grown to full size. `folded`: the right pane is a rail. */
export function useFullChat(): { full: boolean; folded: boolean } {
  const flagOn = useFlag("chat-full");
  const open = useSparkOpen();
  const size = useChatFull((s) => s.full);
  const folded = useChatFull((s) => s.folded);
  const full = flagOn && open && size;
  return { full, folded: full && folded };
}
