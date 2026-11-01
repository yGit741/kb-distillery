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
}));
