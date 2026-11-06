/**
 * The camera that frames a box of pages inside the free area of a canvas: `left` px of its left side lie under a panel,
 * `top` px of its top under the floating search line (and the strip below it), `pad` px of air on the other sides.
 * Pure: ForceGraph.fitIn applies the result, a test checks that the pages land inside the free area.
 */
export interface FitInsets {
  /** px of the canvas's left side covered by a panel */
  left: number;
  /** clearance from the canvas's top edge (search line plus its air); never less than `pad` */
  top: number;
  /** air on the right and bottom, and left of the free area */
  pad: number;
}

export interface FitBox {
  x0: number;
  x1: number;
  y0: number;
  y1: number;
}

/** Zoom ceiling: a lone page is centred at the usual focus zoom, never blown up. */
const MAX_K = 2.2;

export function fitFrame(box: FitBox, width: number, height: number, ins: FitInsets): { x: number; y: number; k: number } {
  // never more clearance than leaves a 40px band to frame in
  const top = Math.min(Math.max(ins.pad, ins.top), Math.max(ins.pad, height - ins.pad - 40));
  const w = Math.max(40, width - ins.left - 2 * ins.pad);
  const h = Math.max(40, height - top - ins.pad);
  const k = Math.min(MAX_K, w / Math.max(1, box.x1 - box.x0), h / Math.max(1, box.y1 - box.y0));
  // the free area's centre sits left/2 px right of, and (top - pad)/2 px below, the canvas centre: the view's centre is
  // that much left of / above the pages' centre
  return {
    x: (box.x0 + box.x1) / 2 - ins.left / 2 / k,
    y: (box.y0 + box.y1) / 2 - (top - ins.pad) / 2 / k,
    k,
  };
}
