import { create } from "zustand";

export type Theme = "light" | "dark";
export const THEME_KEY = "kb-theme";

function systemTheme(): Theme {
  try {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  } catch {
    return "light";
  }
}

/** Saved choice if any, else the OS preference. Storage can throw (private window): never fatal. */
export function readTheme(): Theme {
  try {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved === "light" || saved === "dark") return saved;
  } catch {
    /* ignore */
  }
  return systemTheme();
}

export function applyTheme(theme: Theme): void {
  document.documentElement.classList.toggle("dark", theme === "dark");
}

interface ThemeState {
  theme: Theme;
  set: (theme: Theme) => void;
  toggle: () => void;
  /** Flag graph-corners: a screen that shows its own theme switch says so while it is on screen, so the app bar
   *  drops its own and there is always exactly one. */
  elsewhere: boolean;
  setElsewhere: (on: boolean) => void;
}

export const useTheme = create<ThemeState>((set, get) => ({
  theme: readTheme(),
  set: (theme) => {
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch {
      /* ignore */
    }
    applyTheme(theme);
    set({ theme });
  },
  toggle: () => get().set(get().theme === "dark" ? "light" : "dark"),
  elsewhere: false,
  setElsewhere: (elsewhere) => set({ elsewhere }),
}));
