import { useCallback, useRef, useState } from "react";
import { useDataSource } from "@/api";
import type { Command } from "./commands";
import { routeByRules, type LineRoute } from "./lineRoute";

/** The browser stops waiting for the model after this long and reads the line as a page search. */
export const ROUTE_TIMEOUT_MS = 20_000;

interface Options {
  pages: readonly { id: string; title: string }[];
  commands: readonly Command[];
  canAsk: boolean;
  /** What to do once the line is placed. */
  onRoute: (route: LineRoute) => void;
}

/**
 * Flag line-routing: Enter on a plain line. The rules (./lineRoute) answer at once; a line they cannot place asks
 * `POST /api/line/route` (local app only) while `busy` is true. Any failure, a timeout, or the embedded data reads it as
 * a page search. A newer line, or `cancel`, drops an answer still on its way.
 */
export function useLineRoute(opts: Options): { route: (text: string) => void; cancel: () => void; busy: boolean } {
  const ds = useDataSource();
  const o = useRef(opts);
  o.current = opts;
  const run = useRef(0);
  const [busy, setBusy] = useState(false);

  const route = useCallback(
    (text: string) => {
      const mine = ++run.current;
      const { pages, commands, canAsk } = o.current;
      const ruled = routeByRules(text, { pages, commands, canAsk });
      if (ruled) return o.current.onRoute(ruled);
      if (ds.kind === "embedded") return o.current.onRoute({ intent: "search", text });
      setBusy(true);
      const abort = new AbortController();
      const timer = setTimeout(() => abort.abort(), ROUTE_TIMEOUT_MS);
      const offered = commands.filter((c) => !c.fill).map((c) => ({ id: c.id, label: c.label }));
      ds.routeLine(text, offered, { signal: abort.signal })
        .then(
          (r): LineRoute => {
            if (r.intent === "command") return r.command && commands.some((c) => c.id === r.command) ? { intent: "command", text, id: r.command } : { intent: "search", text };
            if (r.intent === "ask" && !canAsk) return { intent: "search", text };
            return { intent: r.intent, text: r.text || text };
          },
          (): LineRoute => ({ intent: "search", text }),
        )
        .then((r) => {
          clearTimeout(timer);
          if (run.current !== mine) return;
          setBusy(false);
          o.current.onRoute(r);
        });
    },
    [ds],
  );

  const cancel = useCallback(() => {
    run.current++;
    setBusy(false);
  }, []);

  return { route, cancel, busy };
}
