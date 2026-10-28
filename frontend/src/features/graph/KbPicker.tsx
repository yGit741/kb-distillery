import { Library } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useApiQuery } from "@/lib/useApiQuery";

/** `?kbs=a,b` → ids; empty means the server's own knowledge base. */
export const parseKbs = (raw: string | undefined): string[] => [...new Set((raw ?? "").split(",").map((s) => s.trim()).filter(Boolean))];

/**
 * Which knowledge bases the graph shows. Other knowledge bases are read-only; several share one canvas, one
 * region each. The choice lives in the URL (`?kbs=`) so a presentation link reproduces the view.
 */
export function KbPicker({ selected, onChange }: { selected: readonly string[]; onChange: (ids: string[]) => void }) {
  const [open, setOpen] = useState(false);
  const q = useApiQuery(["kb-list"], (d) => d.listKbs());
  const rows = (q.data?.kbs ?? []).filter((k) => !k.error);
  const active = q.data?.active ?? "";
  const shown = selected.length ? selected : active ? [active] : [];
  if (rows.length < 2) return null;
  const toggle = (id: string) => {
    const next = shown.includes(id) ? shown.filter((k) => k !== id) : [...shown, id];
    if (!next.length) return;                    // the canvas always shows at least one knowledge base
    onChange(next.length === 1 && next[0] === active ? [] : rows.map((r) => r.id).filter((k) => next.includes(k)));
  };
  const label = shown.length === 1 ? (rows.find((r) => r.id === shown[0])?.name ?? shown[0]) : `${shown.length} knowledge bases`;
  return (
    <div className="pointer-events-auto absolute right-3 top-3 z-20" data-tour="graph-kbs">
      <Button variant="outline" size="sm" className="h-8 gap-1.5 bg-card/95 shadow-[var(--shadow)]" aria-expanded={open} onClick={() => setOpen(!open)}>
        <Library aria-hidden className="size-4" />
        <span className="max-w-[12rem] truncate">{label}</span>
      </Button>
      {open && (
        <fieldset className="absolute right-0 mt-1 w-64 rounded-lg border bg-card p-2 text-sm shadow-[var(--shadow)]">
          <legend className="sr-only">Knowledge bases on the graph</legend>
          {rows.map((r) => (
            <label key={r.id} className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 hover:bg-accent">
              <input type="checkbox" checked={shown.includes(r.id)} onChange={() => toggle(r.id)} />
              <span className="min-w-0 flex-1 truncate">{r.name || r.id}</span>
              {r.active ? (
                <span className="text-xs text-muted-foreground">this app</span>
              ) : (
                <span className="text-xs text-muted-foreground">view only</span>
              )}
            </label>
          ))}
        </fieldset>
      )}
    </div>
  );
}
