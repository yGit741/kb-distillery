/** Browser-side conveniences (model, template, prompt edits, the open chat). Every access is guarded. */
export function readJson<T>(store: "local" | "session", key: string, fallback: T): T {
  try {
    const s = store === "local" ? window.localStorage : window.sessionStorage;
    const v = s.getItem(key);
    return v === null ? fallback : (JSON.parse(v) as T);
  } catch {
    return fallback;
  }
}

export function writeJson(store: "local" | "session", key: string, value: unknown): void {
  try {
    const s = store === "local" ? window.localStorage : window.sessionStorage;
    s.setItem(key, JSON.stringify(value));
  } catch {
    /* private mode, quota: the screen works without it */
  }
}
