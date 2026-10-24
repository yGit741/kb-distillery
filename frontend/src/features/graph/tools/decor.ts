import { create } from "zustand";

/**
 * What a tool may paint on the canvas without touching it: a halo per page (0..1, drawn as a warning ring)
 * and a fade per link (0..1 multiplies its opacity). One owner at a time; a tool clears its own decor when
 * its panel closes.
 */
export interface Decor {
  owner: string | null;
  halo: ReadonlyMap<string, number> | null;
  linkFade: ((a: string, b: string) => number) | null;
  /** bumped on every change so the canvas redraws */
  tick: number;
  paint: (owner: string, patch: { halo?: ReadonlyMap<string, number> | null; linkFade?: ((a: string, b: string) => number) | null }) => void;
  clear: (owner: string) => void;
}

export const useDecor = create<Decor>((set, get) => ({
  owner: null,
  halo: null,
  linkFade: null,
  tick: 0,
  paint: (owner, patch) => {
    const mine = get().owner === owner;
    set({
      owner,
      halo: patch.halo !== undefined ? patch.halo : mine ? get().halo : null,
      linkFade: patch.linkFade !== undefined ? patch.linkFade : mine ? get().linkFade : null,
      tick: get().tick + 1,
    });
  },
  clear: (owner) => {
    if (get().owner === owner) set({ owner: null, halo: null, linkFade: null, tick: get().tick + 1 });
  },
}));
