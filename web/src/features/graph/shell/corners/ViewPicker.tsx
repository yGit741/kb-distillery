import { cn } from "@/lib/utils";
import { EDGE } from "./geometry";
import { LOOP_TOP, LOOP_W } from "./PinLoop";

/** The graph's views, picked from the pin (flag graph-corners). */
export type GraphView = "concepts" | "sources" | "citations" | "embedding";

export interface ViewOption {
  id: GraphView;
  label: string;
  hint: string;
}

export const VIEW_OPTIONS: readonly ViewOption[] = [
  { id: "concepts", label: "Concepts", hint: "Concepts and the links between them" },
  { id: "sources", label: "Sources", hint: "The sources you read, without the concepts" },
  { id: "citations", label: "Citations", hint: "Papers joined by who cites whom" },
  { id: "embedding", label: "Embedding", hint: "Pages placed by two directions of meaning" },
];

/** A card: a picture of the view over its name. Two cards a row, as wide together as a pinned card. */
const GAP = 6;
export const VIEW_CARD_W = (LOOP_W - GAP) / 2;
const PIC_H = 46;
const NAME_H = 22;
/** The block's height for `count` views; the pinned loop starts below it. */
export function viewPickerHeight(count: number): number {
  const rows = Math.ceil(count / 2);
  return rows ? rows * (PIC_H + NAME_H) + (rows - 1) * GAP + 14 : 0;
}

/**
 * Flag graph-corners: the views the graph can show, at the top of the pin, above the pinned views. Each card has a
 * small picture of what that view looks like (a sketch, not the kb's own pages) and its name; the view on screen
 * has a blue outline and a blue name. This is the one place to switch views with the mouse; the search line still
 * takes `> sources` and the rest by typing.
 */
export function ViewPicker({ open, views, current, onPick }: { open: boolean; views: readonly ViewOption[]; current: GraphView; onPick: (v: GraphView) => void }) {
  return (
    <div
      role="radiogroup"
      aria-label="What the graph shows"
      aria-hidden={!open}
      inert={!open}
      data-corners="views"
      data-tour="graph-subject"
      className={cn("pointer-events-none absolute z-[17] grid grid-cols-2 transition-opacity duration-300 motion-reduce:transition-none", open ? "opacity-100" : "opacity-0")}
      style={{ left: EDGE + 4, top: LOOP_TOP, width: LOOP_W, gap: GAP }}
    >
      {views.map((v) => {
        const on = v.id === current;
        return (
          <button
            key={v.id}
            type="button"
            role="radio"
            aria-checked={on}
            data-view-option={v.id}
            title={v.hint}
            onClick={() => onPick(v.id)}
            className={cn(
              "pointer-events-auto relative overflow-hidden rounded-[10px] border bg-card text-left shadow-[var(--shadow)] transition-[border-color,box-shadow] duration-150 motion-reduce:transition-none",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              on ? "border-primary ring-1 ring-primary" : "hover:border-primary",
            )}
            style={{ width: VIEW_CARD_W, height: PIC_H + NAME_H }}
          >
            <ViewSketch id={v.id} className="block w-full" style={{ height: PIC_H }} />
            <span className={cn("flex items-center gap-1.5 border-t px-2 text-[12px]", on ? "font-semibold text-primary" : "text-foreground")} style={{ height: NAME_H }}>
              {on && <span aria-hidden className="size-1.5 flex-none rounded-full bg-primary" />}
              {v.label}
            </span>
          </button>
        );
      })}
    </div>
  );
}

/** A small, fixed picture of each view, drawn in the chrome's own greys and its one accent. */
function ViewSketch({ id, className, style }: { id: GraphView; className?: string; style?: React.CSSProperties }) {
  return (
    <svg viewBox="0 0 90 46" preserveAspectRatio="xMidYMid meet" className={className} style={style} aria-hidden>
      <rect width="90" height="46" className="fill-card" />
      {id === "concepts" && <ConceptsArt />}
      {id === "sources" && <SourcesArt />}
      {id === "citations" && <CitationsArt />}
      {id === "embedding" && <EmbeddingArt />}
    </svg>
  );
}

/** A dot is a round-capped stroke of no length (as in ./Thumb): these sketches are pictures, not node marks. */
function Dot({ x, y, r, className }: { x: number; y: number; r: number; className: string }) {
  return <path d={`M${x} ${y}h.01`} strokeLinecap="round" strokeWidth={r * 2} className={className} />;
}

const RINGS: readonly [number, number][] = [
  [20, 14], [34, 26], [48, 12], [58, 30], [72, 18], [26, 34], [44, 36], [66, 8],
];
function ConceptsArt() {
  const links: readonly [number, number][] = [[0, 1], [1, 2], [1, 3], [2, 4], [3, 4], [1, 5], [3, 6], [2, 7], [5, 6]];
  return (
    <>
      <g className="stroke-border" strokeWidth=".8">
        {links.map(([a, b], i) => (
          <line key={i} x1={RINGS[a]![0]} y1={RINGS[a]![1]} x2={RINGS[b]![0]} y2={RINGS[b]![1]} />
        ))}
      </g>
      {RINGS.map(([x, y], i) => (
        <g key={i}>
          <Dot x={x} y={y} r={3.9} className={i === 1 ? "stroke-primary" : "stroke-muted-foreground"} />
          <Dot x={x} y={y} r={2.9} className="stroke-card" />
          <Dot x={x} y={y} r={1} className={i === 1 ? "stroke-primary" : "stroke-muted-foreground"} />
        </g>
      ))}
    </>
  );
}

function SourcesArt() {
  const dots: readonly [number, number][] = [
    [16, 12], [24, 20], [14, 28], [30, 32], [36, 14], [44, 24], [52, 36], [58, 12], [64, 26], [72, 34], [76, 14], [40, 38], [22, 38], [68, 8], [50, 18],
  ];
  return (
    <>
      <g className="stroke-border" strokeWidth=".6">
        <line x1="16" y1="12" x2="36" y2="14" />
        <line x1="36" y1="14" x2="50" y2="18" />
        <line x1="44" y1="24" x2="64" y2="26" />
        <line x1="58" y1="12" x2="76" y2="14" />
      </g>
      {dots.map(([x, y], i) => (
        <Dot key={i} x={x} y={y} r={2.6} className={i % 5 === 0 ? "stroke-primary" : "stroke-muted-foreground"} />
      ))}
    </>
  );
}

function CitationsArt() {
  // one founding paper, cited by a few, each cited in turn: arrows point at the paper that is cited
  const nodes: readonly [number, number, number][] = [
    [45, 9, 4.2], [24, 24, 2.8], [45, 25, 2.8], [66, 24, 2.8], [14, 38, 2], [30, 38, 2], [52, 38, 2], [74, 38, 2],
  ];
  const cites: readonly [number, number][] = [[1, 0], [2, 0], [3, 0], [4, 1], [5, 1], [6, 2], [7, 3], [5, 2]];
  return (
    <>
      <defs>
        <marker id="kb-view-cite" viewBox="0 0 6 6" refX="5" refY="3" markerWidth="4" markerHeight="4" orient="auto">
          <path d="M0 0 6 3 0 6z" className="fill-muted-foreground" />
        </marker>
      </defs>
      <g className="stroke-muted-foreground" strokeWidth=".7">
        {cites.map(([a, b], i) => {
          const [x1, y1] = nodes[a]!;
          const [x2, y2, r] = nodes[b]!;
          const d = Math.hypot(x2 - x1, y2 - y1);
          return <line key={i} x1={x1} y1={y1} x2={x2 - ((x2 - x1) * (r + 1)) / d} y2={y2 - ((y2 - y1) * (r + 1)) / d} markerEnd="url(#kb-view-cite)" />;
        })}
      </g>
      {nodes.map(([x, y, r], i) => (
        <Dot key={i} x={x} y={y} r={r} className={i === 0 ? "stroke-primary" : "stroke-muted-foreground"} />
      ))}
    </>
  );
}

function EmbeddingArt() {
  // two axes of meaning and the pages placed on them, in two loose clumps
  const pts: readonly [number, number][] = [
    [22, 14], [26, 18], [19, 20], [30, 13], [24, 24], [58, 28], [62, 32], [66, 26], [56, 34], [70, 31], [44, 20], [40, 30],
  ];
  return (
    <>
      <g className="stroke-border" strokeWidth=".8">
        <line x1="10" y1="40" x2="82" y2="40" />
        <line x1="10" y1="40" x2="10" y2="6" />
      </g>
      {pts.map(([x, y], i) => (
        <Dot key={i} x={x} y={y} r={2.2} className={i < 5 ? "stroke-primary" : "stroke-muted-foreground"} />
      ))}
    </>
  );
}
