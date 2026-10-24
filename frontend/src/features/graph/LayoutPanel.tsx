import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { CheckField, RangeField } from "./controls";
import { useGraphUi } from "./store";

export function LayoutPanel({ onReheat, onRefresh, refreshing, stats }: { onReheat: () => void; onRefresh: () => void; refreshing: boolean; stats: string }) {
  const ui = useGraphUi();
  return (
    <div className="flex flex-col gap-3">
      <RangeField label="Charge" value={ui.charge} min={-400} max={-20} step={10} onChange={(charge) => ui.set({ charge })} />
      <RangeField label="Link distance" value={ui.linkDistance} min={20} max={200} step={5} onChange={(linkDistance) => ui.set({ linkDistance })} />
      <RangeField label="Centre gravity" value={ui.gravity} min={0} max={1} step={0.05} onChange={(gravity) => ui.set({ gravity })} />
      <Button variant="secondary" size="sm" className="self-start" onClick={onReheat}>
        Reheat layout
      </Button>
      <hr />
      <CheckField label="Live sync (poll the wiki)" checked={ui.liveSync} onChange={(liveSync) => ui.set({ liveSync })} />
      <Button variant="secondary" size="sm" className="self-start" onClick={onRefresh} disabled={refreshing}>
        <RefreshCw aria-hidden className={refreshing ? "animate-spin" : ""} /> Refresh now
      </Button>
      <p className="text-xs text-muted-foreground">{stats}</p>
    </div>
  );
}
