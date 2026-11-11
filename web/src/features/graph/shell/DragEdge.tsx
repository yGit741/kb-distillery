import { cn } from "@/lib/utils";

/**
 * A thin edge that shows a line on hover and resizes what it sits on when dragged. `axis` x is a vertical edge on the
 * right side, y a horizontal edge on the top; `onDrag` gets the pointer's travel and the size when the drag began.
 */
export function DragEdge({
  label,
  axis,
  testId,
  start,
  onDrag,
  className,
}: {
  label: string;
  axis: "x" | "y";
  testId: string;
  start: number;
  onDrag: (d: number, start: number) => void;
  className?: string;
}) {
  const x = axis === "x";
  return (
    <div
      role="separator"
      aria-orientation={x ? "vertical" : "horizontal"}
      aria-label={label}
      tabIndex={0}
      data-testid={testId}
      className={cn(
        "pointer-events-auto absolute z-10 after:absolute after:bg-transparent after:transition-colors hover:after:bg-ring focus-visible:outline-none focus-visible:after:bg-ring",
        x
          ? "inset-y-0 -right-1 w-2 cursor-col-resize after:inset-y-0 after:left-1/2 after:w-px after:-translate-x-1/2"
          : "inset-x-0 -top-1 h-2 cursor-row-resize after:inset-x-0 after:top-1/2 after:h-px after:-translate-y-1/2",
        className,
      )}
      onPointerDown={(e) => {
        e.preventDefault();
        const p0 = x ? e.clientX : e.clientY;
        const move = (ev: PointerEvent) =>
          onDrag((x ? ev.clientX : ev.clientY) - p0, start);
        const up = () => {
          window.removeEventListener("pointermove", move);
          window.removeEventListener("pointerup", up);
          window.removeEventListener("pointercancel", up);
          document.body.style.cursor = "";
        };
        document.body.style.cursor = x ? "col-resize" : "row-resize";
        window.addEventListener("pointermove", move);
        window.addEventListener("pointerup", up);
        window.addEventListener("pointercancel", up);
      }}
      onKeyDown={(e) => {
        const step =
          e.key === (x ? "ArrowRight" : "ArrowDown")
            ? 16
            : e.key === (x ? "ArrowLeft" : "ArrowUp")
              ? -16
              : 0;
        if (step) onDrag(step, start);
      }}
    />
  );
}
