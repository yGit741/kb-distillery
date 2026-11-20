/** Passages the owner marks on a card: at most MAX_MARKS, each cut to MARK_CHARS. */
export const MAX_MARKS = 5;
export const MARK_CHARS = 600;
export const HIGHLIGHT = "review-mark";

/** Add a passage unless it is empty, already there, or the limit is reached. */
export function addMark(marks: string[], text: string): string[] {
  const t = text.trim().slice(0, MARK_CHARS);
  if (!t || marks.length >= MAX_MARKS || marks.includes(t)) return marks;
  return [...marks, t];
}

/** The DOM range of `text` inside `root` (across text nodes, never inside a form field), or null. */
export function findRange(root: Node, text: string): Range | null {
  const doc = root.ownerDocument ?? document;
  const walker = doc.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: (n) => ((n.parentElement?.closest("input,textarea,button") ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT)),
  });
  const nodes: Text[] = [];
  let all = "";
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    nodes.push(n as Text);
    all += (n as Text).data;
  }
  const start = all.indexOf(text);
  if (start < 0) return null;
  const end = start + text.length;
  const range = doc.createRange();
  let pos = 0;
  let begun = false;
  for (const n of nodes) {
    const next = pos + n.data.length;
    if (!begun && start < next) {
      range.setStart(n, start - pos);
      begun = true;
    }
    if (begun && end <= next) {
      range.setEnd(n, end - pos);
      return range;
    }
    pos = next;
  }
  return null;
}

type HighlightCtor = new (...ranges: Range[]) => unknown;
type Registry = { set: (name: string, h: unknown) => void; delete: (name: string) => void };

/** Paint the marks with the CSS Custom Highlight API where the browser has it; a no-op elsewhere. */
export function paintMarks(root: Node | null, marks: string[]): () => void {
  const H = (globalThis as { Highlight?: HighlightCtor }).Highlight;
  const reg = (globalThis.CSS as unknown as { highlights?: Registry } | undefined)?.highlights;
  if (!H || !reg) return () => undefined;
  const ranges = root ? marks.map((m) => findRange(root, m)).filter((r): r is Range => !!r) : [];
  if (ranges.length) reg.set(HIGHLIGHT, new H(...ranges));
  else reg.delete(HIGHLIGHT);
  return () => reg.delete(HIGHLIGHT);
}
