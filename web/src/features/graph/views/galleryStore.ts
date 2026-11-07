import { create } from "zustand";

/** Whether the view gallery window is open (flag graph-intent). Opened by `/views`, `/gallery` and the pin corner. */
interface GalleryState {
  open: boolean;
  show: () => void;
  hide: () => void;
}

export const useGallery = create<GalleryState>((set) => ({
  open: false,
  show: () => set({ open: true }),
  hide: () => set({ open: false }),
}));

export const resetGallery = () => useGallery.setState({ open: false });
