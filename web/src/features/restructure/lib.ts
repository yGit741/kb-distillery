/** Pure helpers of the restructure dialogs: slash commands, cut placement, range picking. */
export type RestructureKind = "merge" | "split" | "extract";
export const KINDS: readonly RestructureKind[] = ["merge", "split", "extract"];

export type SlashCommand = { kind: RestructureKind; mentions: string[] };

/** "/merge @beta" typed in the page chat (mentions picked with the @ picker arrive as chips, typed ones are read here). */
export function parseSlash(message: string, mentioned: readonly string[] = []): SlashCommand | null {
  const m = /^\s*\/(merge|split|extract)\b(.*)$/is.exec(message);
  if (!m) return null;
  const typed = [...m[2]!.matchAll(/@([\w.-]+)/g)].map((x) => x[1]!);
  return { kind: m[1]!.toLowerCase() as RestructureKind, mentions: [...new Set([...mentioned, ...typed])] };
}

/** The commands whose name starts with what is typed after the slash (for the hint list). */
export function slashMatches(draft: string): RestructureKind[] {
  const m = /^\s*\/([a-z]*)$/i.exec(draft);
  return m ? KINDS.filter((k) => k.startsWith(m[1]!.toLowerCase())) : [];
}

/** Place a cut before block `at`, or remove it when one is already there. Always sorted. */
export function toggleCut(cuts: readonly number[], at: number): number[] {
  return cuts.includes(at) ? cuts.filter((c) => c !== at) : [...cuts, at].sort((a, b) => a - b);
}

export type Range = { from: number; to: number; open: boolean };

/** First click starts a range, the second ends it (either order), a third starts again. */
export function pickRange(r: Range | null, i: number): Range {
  if (!r || !r.open) return { from: i, to: i, open: true };
  return { from: Math.min(r.from, i), to: Math.max(r.from, i), open: false };
}

export const clip = (s: string, n: number) => {
  const t = s.replace(/\s+/g, " ").trim();
  return t.length > n ? `${t.slice(0, n - 1)}…` : t;
};
