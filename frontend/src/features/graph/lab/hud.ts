import { create } from "zustand";

/** Live readouts of the label layer, shown at the foot of the rail (the lab's HUD). */
export interface LabHud {
  zoom: number;
  labels: number;
  onScreen: number;
  concepts: number;
  conceptsVisible: number;
  coverage: number;
  dropped: number;
  churn: number;
  minPx: number;
  /** the committed hover (the hover card reads it; the canvas writes it once per change) */
  hover: string | null;
}

export const useLabHud = create<LabHud & { set: (h: Omit<LabHud, "hover">) => void }>((set) => ({
  zoom: 1,
  labels: 0,
  onScreen: 0,
  concepts: 0,
  conceptsVisible: 0,
  coverage: 0,
  dropped: 0,
  churn: 0,
  minPx: Infinity,
  hover: null,
  set: (h) => set(h),
}));
