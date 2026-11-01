import { useDataSource } from "@/api";
import { Button } from "@/components/ui/button";
import { pileColor } from "@/theme/palette";
import { useLayer } from "../layerStore";
import { useGraphUi } from "../store";
import { pileOf } from "../rawLayer";
import { pageIds } from "../selection";
import type { GraphToolContext } from ".";

/**
 * The data layer: switch the raw piles on (one pile per format, sized by file count, ringed by the digested
 * share), open a pile's files, or list the raw files behind the selected pages.
 */
/** On a phone the panel would cover the drawer it just opened. */
const dismissOnPhone = () => {
  if (typeof window !== "undefined" && window.matchMedia?.("(max-width: 639px)").matches) useGraphUi.setState({ flyout: null });
};

export function RawPanel({ ctx }: { ctx: GraphToolContext }) {
  const ds = useDataSource();
  const rawOn = useLayer((s) => s.rawOn);
  const drawer = useLayer((s) => s.drawer);
  const piles = ctx.model.raw?.piles ?? [];
  const ids = pageIds(ctx.selection, ctx.byId);
  const shared = ds.kind === "embedded";

  return (
    <div className="flex flex-col gap-3 text-sm">
      <label className="flex items-start gap-2">
        <input type="checkbox" className="mt-1" checked={rawOn} disabled={shared} onChange={(e) => useLayer.getState().setRaw(e.target.checked)} />
        <span>
          Show raw files as piles
          <span className="block text-xs text-muted-foreground">{shared ? "Not in the shared snapshot: raw files stay private." : "One pile per format, tied to the pages it feeds. Loads the whole corpus, so it refreshes slowly."}</span>
        </span>
      </label>
      {rawOn && piles.length > 0 && (
        <ul aria-label="Piles" className="flex flex-col gap-0.5">
          {piles.map((p) => {
            const info = pileOf(p);
            if (!info) return null;
            const on = drawer?.kind === "format" && drawer.format === info.format;
            return (
              <li key={p.id}>
                <button
                  type="button"
                  aria-pressed={on}
                  className="flex w-full items-center gap-2 rounded px-1.5 py-1 text-left hover:bg-accent aria-pressed:bg-accent"
                  onClick={() => {
                    useLayer.getState().openDrawer(on ? null : { kind: "format", format: info.format });
                    if (!on) dismissOnPhone();
                  }}
                >
                  <i className="size-2.5 shrink-0 rounded-full" style={{ background: pileColor(info.format) }} />
                  <span className="min-w-0 flex-1 truncate">{info.format}</span>
                  <span className="text-xs text-muted-foreground">
                    {info.count} · {Math.round(info.share * 100)}% digested
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
      {rawOn && piles.length === 0 && <p className="text-xs text-muted-foreground">Loading the data layer…</p>}
      <Button
        size="sm"
        variant="outline"
        disabled={!ids.length || shared}
        onClick={() => {
          useLayer.getState().openDrawer(drawer?.kind === "selection" ? null : { kind: "selection" });
          if (drawer?.kind !== "selection") dismissOnPhone();
        }}
      >
        Raw files behind {ids.length} selected page{ids.length === 1 ? "" : "s"}
      </Button>
    </div>
  );
}
