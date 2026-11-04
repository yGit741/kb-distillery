import { useSyncExternalStore } from "react";

const QUERY = "(prefers-reduced-motion: reduce)";
const mq = () => (typeof matchMedia === "function" ? matchMedia(QUERY) : null);

/** True while the system asks for less motion: the fans, the legends and the lens then settle at once. */
export function useReducedMotion(): boolean {
  return useSyncExternalStore(
    (cb) => {
      const m = mq();
      m?.addEventListener?.("change", cb);
      return () => m?.removeEventListener?.("change", cb);
    },
    () => mq()?.matches ?? false,
    () => false,
  );
}
