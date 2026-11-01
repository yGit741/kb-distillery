/** Prompt presets (templates from the server) plus the user's per-template edits kept in this browser. */
export interface Prompt {
  id: string;
  title: string;
  description: string;
  text: string;
}
export type Edits = Record<string, string>;

const str = (v: unknown) => (typeof v === "string" ? v : "");

export function parsePrompts(raw: { [key: string]: unknown }[]): Prompt[] {
  return raw
    .map((p) => ({ id: str(p.id), title: str(p.title) || str(p.id), description: str(p.description), text: str(p.text) }))
    .filter((p) => p.id);
}

export const pick = (prompts: Prompt[], id: string): Prompt | undefined => prompts.find((p) => p.id === id) ?? prompts[0];

/** The system prompt that will be sent: the user's edit, else the template. */
export const systemFor = (p: Prompt | undefined, edits: Edits): string => (p ? (edits[p.id] ?? p.text) : "");

export const isCustom = (p: Prompt | undefined, edits: Edits): boolean =>
  !!p && p.id in edits && edits[p.id]!.trim() !== p.text.trim();

/** Store an edit, or drop it when the text is back to the template. */
export function setEdit(p: Prompt, edits: Edits, text: string): Edits {
  const next = { ...edits };
  if (text.trim() === p.text.trim()) delete next[p.id];
  else next[p.id] = text;
  return next;
}
