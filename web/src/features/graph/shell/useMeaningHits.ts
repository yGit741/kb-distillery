import { useEffect, useState } from "react";
import { useDataSource } from "@/api";

/** The typing pause before the meaning service is asked: it is never called per keystroke. */
export const MEANING_PAUSE_MS = 350;
const SHOWN_MAX = 8;

export interface MeaningHit {
  slug: string;
  score: number;
}

/**
 * "Related by meaning" (flags graph-intent and semantic-search): after a pause in typing, the pages close in meaning to
 * `text`, best first. A newer text cancels the request still on its way; the hits of an older text are dropped the moment
 * the text changes, so they never sit under words they do not answer. Any failure (service off or down) is no hits.
 */
export function useMeaningHits(text: string, enabled: boolean): MeaningHit[] {
  const ds = useDataSource();
  const [state, setState] = useState<{ text: string; hits: MeaningHit[] }>({ text: "", hits: [] });
  const q = text.trim();
  const active = enabled && q.length >= 2;
  useEffect(() => {
    if (!active) return;
    const ctl = new AbortController();
    const t = window.setTimeout(() => {
      ds.searchSimilar({ q, k: SHOWN_MAX * 2 }, ctl.signal).then(
        (r) => {
          if (!ctl.signal.aborted) setState({ text: q, hits: r.hits.map((h) => ({ slug: h.slug, score: h.score })) });
        },
        () => {
          if (!ctl.signal.aborted) setState({ text: q, hits: [] });
        },
      );
    }, MEANING_PAUSE_MS);
    return () => {
      window.clearTimeout(t);
      ctl.abort();
    };
  }, [ds, q, active]);
  return active && state.text === q ? state.hits : [];
}
