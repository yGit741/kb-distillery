import { useUi } from "@/app/ui-store";
import { useKb } from "@/lib/store";
import { print } from "./layers/grammar";
import { useLayers } from "./layers/store";

/**
 * Think from the action menu (flag graph-intent): opens the quick capture with the pages attached. A page that is part
 * of the focus brings the whole focus; when a view is applied its query lines ride along as a footer.
 */
export function openCaptureAbout(ids: string[]): void {
  const focus = [...useKb.getState().selection];
  const all = ids.length === 1 && focus.length > 1 && focus.includes(ids[0]!) ? focus : ids;
  const view = useLayers.getState().stack.layers.map(print);
  useUi.getState().openCapture({ ids: all, view });
}
