import { useKb } from "@/lib/store";
import { chatDraft } from "../tools/chatDockStore";
import { evaluate } from "../layers/model";
import { useLayers } from "../layers/store";
import { useGraphUi } from "../store";
import { LINE_COPY } from "./copy";

/** The pages the view draws now, or none when it draws the whole graph (nothing to narrow the chat to). */
export function shownIds(): string[] {
  const v = useGraphUi.getState().view;
  if (v) return [...v.shown];
  const { graph, stack } = useLayers.getState();
  const ids = graph && stack.layers.length ? evaluate(stack, graph).nodeIds : null;
  return ids ? [...ids] : [];
}

/** The draft the chat opens with: the question, the focused pages (or `focus`) and the shown pages (capped). Shared by the Ask row and the chat action. */
export function chatContextDraft(question: string, focus: readonly string[] = [...useKb.getState().selection]): string {
  return chatDraft(question, focus, shownIds(), LINE_COPY.chatContext);
}
