import { cn } from "@/lib/utils";
import { NodeSwatch } from "../encoding/NodeMarkSvg";
import { degreeOf, type GNode } from "../types";
import { useLabHud } from "./hud";

/**
 * The hovered page at a glance, bottom-left: title, type, link count and the first lines of its preview. Reads the
 * committed hover the canvas writes to the HUD store; nothing on touch screens, where there is no hover.
 */
export function HoverCard({ byId, className }: { byId: ReadonlyMap<string, GNode>; className?: string }) {
  const id = useLabHud((s) => s.hover);
  const n = id ? byId.get(id) : undefined;
  if (!n) return null;
  const preview = (n.preview || "").split(/\n+/).map((l) => l.trim()).filter(Boolean).slice(0, 2).join(" ");
  return (
    <div
      role="status"
      aria-live="polite"
      data-testid="hover-card"
      className={cn("pointer-events-none w-72 max-w-[calc(100%-4.5rem)] rounded-lg border bg-card/95 px-3 py-2 text-sm shadow-[var(--shadow)] [@media(pointer:coarse)]:hidden max-sm:hidden", className)}
    >
      <div className="flex items-center gap-1.5 font-medium">
        <NodeSwatch type={n.type} className="size-3.5 text-muted-foreground" /> <span className="truncate">{n.title || n.id}</span>
      </div>
      <p className="text-xs text-muted-foreground">
        {n.type} · {degreeOf(n)} link{degreeOf(n) === 1 ? "" : "s"}
      </p>
      {preview && <p className="mt-1 line-clamp-2 text-xs leading-snug text-foreground/80">{preview}</p>}
    </div>
  );
}
