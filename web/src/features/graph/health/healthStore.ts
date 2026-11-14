import { create } from "zustand";
import type { SourceGlyph } from "../encoding/spec";

/** The Health view's one piece of state: the source kind the user is inside (null = the map with the dial). */
export const useHealth = create<{ inside: SourceGlyph | null; enter: (kind: SourceGlyph) => void; leave: () => void }>((set) => ({
  inside: null,
  enter: (inside) => set({ inside }),
  leave: () => set({ inside: null }),
}));
