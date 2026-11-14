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
  /** clearance from the bottom edge when controls sit there (the subject switch); never less than `pad` */
  bottom?: number;
  /** px of the canvas's right side covered by a panel (an open legend), on top of `pad` */
  right?: number;
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
  const bottom = Math.min(Math.max(ins.pad, ins.bottom ?? ins.pad), Math.max(ins.pad, height / 3));
  const top = Math.min(Math.max(ins.pad, ins.top), Math.max(ins.pad, height - bottom - 40));
  const right = Math.min(Math.max(0, ins.right ?? 0), width / 3);
  const w = Math.max(40, width - ins.left - right - 2 * ins.pad);
  const h = Math.max(40, height - top - bottom);
  const k = Math.min(MAX_K, w / Math.max(1, box.x1 - box.x0), h / Math.max(1, box.y1 - box.y0));
  // the free area's centre sits left/2 px right of, and (top - pad)/2 px below, the canvas centre: the view's centre is
  // that much left of / above the pages' centre
  return {
    x: (box.x0 + box.x1) / 2 - (ins.left - right) / 2 / k,
    y: (box.y0 + box.y1) / 2 - (top - bottom) / 2 / k,
    k,
  };
}
