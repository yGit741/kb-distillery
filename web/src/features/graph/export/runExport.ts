import type { DataSource } from "@/api";
import { LINE_COPY } from "../shell/copy";
import { buildBundle, type SourcePage } from "./okfBundle";

const CONCURRENCY = 6;

export async function copyText(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
    return;
  } catch {
    /* fall through to the textarea */
  }
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.cssText = "position:fixed;opacity:0;pointer-events:none";
  document.body.appendChild(ta);
  ta.select();
  try {
    document.execCommand("copy");
  } finally {
    ta.remove();
  }
}

async function fetchAll(ds: DataSource, slugs: string[]): Promise<SourcePage[]> {
  const out: Array<SourcePage | null> = new Array(slugs.length).fill(null);
  let next = 0;
  const worker = async () => {
    for (let i = next++; i < slugs.length; i = next++) {
      try {
        out[i] = { slug: slugs[i]!, source: await ds.getPageSource(slugs[i]!) };
      } catch {
        out[i] = null;
      }
    }
  };
  await Promise.all(Array.from({ length: Math.min(CONCURRENCY, slugs.length) }, worker));
  return out.filter((p): p is SourcePage => p !== null);
}

/** Copy these pages as an OKF bundle and say so. The shared site never includes `## My notes`. */
export async function exportPages(
  ds: DataSource,
  slugs: string[],
  o: { kbName: string; isShare: boolean; say: (text: string) => void },
): Promise<void> {
  const pages = await fetchAll(ds, [...new Set(slugs)]);
  if (!pages.length) {
    o.say(LINE_COPY.exportNone);
    return;
  }
  const b = buildBundle(pages, { includeNotes: !o.isShare, kbName: o.kbName });
  try {
    await copyText(b.text);
  } catch {
    o.say(LINE_COPY.exportFailed);
    return;
  }
  const line = LINE_COPY.exported(pages.length - b.cut.length);
  o.say(b.cut.length ? `${line} ${b.cut.length} pages not included: ${b.cut.slice(0, 8).join(", ")}${b.cut.length > 8 ? ", …" : ""}` : line);
}
