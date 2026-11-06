import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { visibleItems, type MenuContext, type MenuItem } from "./menu";
import { NodeSwatch } from "./encoding/NodeMarkSvg";
import type { ColorBy } from "./style";
import type { GNode } from "./types";
import { swatchColor } from "./nodeColor";

interface Props {
  node: GNode;
  x: number;
  y: number;
  colorBy: ColorBy;
  ctx: MenuContext;
  items?: readonly MenuItem[];
  /** A set of pages instead of one page: the header says this and shows no swatch. */
  title?: string;
  onClose: () => void;
}

/** The right-click menu on a page. Entries come from MENU_ITEMS (./menu). */
export function NodeMenu({ node, x, y, colorBy, ctx, items, title, onClose }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ left: x, top: y });
  const list = visibleItems(node, items);

  useLayoutEffect(() => {
    const r = ref.current?.getBoundingClientRect();
    if (!r) return;
    setPos({
      left: Math.max(8, Math.min(x, window.innerWidth - r.width - 8)),
      top: Math.max(8, Math.min(y, window.innerHeight - r.height - 8)),
    });
    ref.current?.querySelector<HTMLButtonElement>("button:not([disabled])")?.focus({ preventScroll: true });
  }, [x, y]);

  useEffect(() => {
    const down = (e: PointerEvent) => {
      if (!ref.current?.contains(e.target as Node)) onClose();
    };
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
        return;
      }
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
      e.preventDefault();
      const all = [...(ref.current?.querySelectorAll<HTMLButtonElement>("button:not([disabled])") ?? [])];
      const i = all.indexOf(document.activeElement as HTMLButtonElement);
      all[(i + (e.key === "ArrowDown" ? 1 : -1) + all.length) % all.length]?.focus();
    };
    document.addEventListener("pointerdown", down, true);
    document.addEventListener("keydown", key, true);
    window.addEventListener("blur", onClose);
    window.addEventListener("wheel", onClose, { passive: true });
    return () => {
      document.removeEventListener("pointerdown", down, true);
      document.removeEventListener("keydown", key, true);
      window.removeEventListener("blur", onClose);
      window.removeEventListener("wheel", onClose);
    };
  }, [onClose]);

  return (
    <div
      ref={ref}
      role="menu"
      aria-label={`Actions for ${title ?? (node.title || node.id)}`}
      className="fixed z-50 min-w-56 rounded-lg border bg-popover p-1 text-popover-foreground shadow-[var(--shadow)]"
      style={pos}
    >
      <div className="flex items-center gap-2 border-b px-2 py-1.5 text-xs text-muted-foreground">
        {title === undefined && <NodeSwatch type={node.type} color={swatchColor(node, colorBy)} />}
        <span className="max-w-64 truncate">{title ?? (node.title || node.id)}</span>
      </div>
      {list.map((it) => {
        const on = !it.enabled || it.enabled(node);
        return (
          <button
            key={it.id}
            type="button"
            role="menuitem"
            disabled={!on}
            className="flex w-full items-center justify-between gap-4 rounded px-2 py-1.5 text-left text-sm hover:bg-accent focus-visible:bg-accent disabled:opacity-50"
            onClick={() => {
              onClose();
              it.run(node, ctx);
            }}
          >
            <span>{it.labelOf?.(node) ?? it.label}</span>
            <small className="text-muted-foreground">{on ? it.hint : it.why}</small>
          </button>
        );
      })}
    </div>
  );
}
