import { link } from "@/lib/links";

/** The `@word` being typed at the end of the text, if any (flag `chat-full`'s page mention). */
export function openMention(text: string): { start: number; query: string } | null {
  const m = /(^|\s)@([^\s@]*)$/.exec(text);
  return m ? { start: m.index + m[1]!.length, query: m[2]! } : null;
}

/** Pages whose title or slug matches the query: those starting with it first. */
export function matchPages(pages: readonly { id: string; title: string }[], query: string, max = 6): { id: string; title: string }[] {
  const q = query.toLowerCase();
  const hit = (p: { id: string; title: string }) => `${p.title} ${p.id}`.toLowerCase().includes(q);
  const head = (p: { id: string; title: string }) => p.title.toLowerCase().startsWith(q) || p.id.toLowerCase().startsWith(q);
  const all = pages.filter(hit);
  return [...all.filter(head), ...all.filter((p) => !head(p))].slice(0, max);
}

/** Turn each `@slug` of a known page into its page link, so the agent reads exactly that page. */
export function linkMentions(text: string, pages: readonly { id: string; title: string }[]): string {
  const known = new Map(pages.map((p) => [p.id, p] as const));
  return text.replace(/(^|\s)@([^\s@]+)/g, (all, pre: string, slug: string) => {
    const p = known.get(slug);
    return p ? `${pre}${link(p.id, p.title)}` : all;
  });
}

/** The fence for a text: a run of backticks longer than any run inside it (three at least). */
export function fenceFor(text: string): string {
  const longest = Math.max(0, ...(text.match(/`+/g) ?? []).map((r) => r.length));
  return "`".repeat(Math.max(3, longest + 1));
}

/** Text files attached to a message are sent inline, each in its own fenced block. */
export function withAttachments(text: string, files: readonly { name: string; text: string }[]): string {
  if (!files.length) return text;
  const blocks = files.map((f) => {
    const fence = fenceFor(f.text);
    return `Attached file ${f.name}:\n${fence}\n${f.text}\n${fence}`;
  });
  return `${text}\n\n${blocks.join("\n\n")}`;
}
