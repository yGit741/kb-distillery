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
}

export const useLabHud = create<LabHud & { set: (h: LabHud) => void }>((set) => ({
  zoom: 1,
  labels: 0,
  onScreen: 0,
  concepts: 0,
  conceptsVisible: 0,
  coverage: 0,
  dropped: 0,
  churn: 0,
  minPx: Infinity,
  set: (h) => set(h),
}));
