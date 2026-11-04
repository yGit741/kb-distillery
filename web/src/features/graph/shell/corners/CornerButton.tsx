import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import { BUTTON } from "./geometry";

/** The tilted pushpin: a hollow head and a sharp filled needle (the pinned views). 26px. */
export function PushPin({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
      <g transform="rotate(45 12 12)">
        <path d="M8.4 3.3h7.2l-.9 1.5c-.8 1.4-1 3-.6 4.6l.3 1.1 2.6 1.9v1.2H7v-1.2l2.6-1.9.3-1.1c.4-1.6.2-3.2-.6-4.6z" strokeLinejoin="miter" strokeLinecap="butt" />
        <path d="M10.5 14.2h3L12 21.6z" fill="currentColor" stroke="none" />
      </g>
    </svg>
  );
}

/** Three small dots: the "..." beside a corner button (round-capped strokes, so they match the icons' line ends). */
export function Dots() {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" aria-hidden>
      <path d="M3.5 8h.01M8 8h.01M12.5 8h.01" />
    </svg>
  );
}

const RING = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

interface Props extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> {
  label: string;
  on?: boolean;
  children: ReactNode;
}

/** A corner button: a bare icon, a faint round fill on hover or while its panel is open. No card behind it. */
export const CornerButton = forwardRef<HTMLButtonElement, Props>(function CornerButton({ label, on, className, style, children, ...rest }, ref) {
  return (
    <button
      ref={ref}
      type="button"
      aria-label={label}
      title={label}
      aria-expanded={on}
      className={cn(
        "pointer-events-auto grid place-items-center rounded-full text-muted-foreground transition-[background-color,color,transform] duration-200 hover:bg-foreground/[0.07] hover:text-foreground active:scale-90 motion-reduce:transition-none",
        on && "bg-primary/[0.14] text-primary hover:bg-primary/[0.14] hover:text-primary",
        RING,
        className,
      )}
      style={{ width: BUTTON, height: BUTTON, ...style }}
      {...rest}
    >
      {children}
    </button>
  );
});

/** The small round "..." beside a corner button. */
export const MoreButton = forwardRef<HTMLButtonElement, Omit<Props, "children">>(function MoreButton({ label, on, className, ...rest }, ref) {
  return (
    <button
      ref={ref}
      type="button"
      aria-label={label}
      title={label}
      aria-haspopup="menu"
      aria-expanded={on}
      className={cn(
        "pointer-events-auto grid size-7 place-items-center rounded-full text-muted-foreground transition-colors hover:bg-foreground/[0.07] hover:text-foreground motion-reduce:transition-none",
        on && "bg-foreground/[0.07] text-foreground",
        RING,
        className,
      )}
      {...rest}
    >
      <Dots />
    </button>
  );
});

/** The row of actions a "..." opens: a small pill beside the button, so it never covers the fan or the list. */
export function ActionPill({ label, align, children, className }: { label: string; align: "left" | "right"; children: ReactNode; className?: string }) {
  return (
    <div
      role="menu"
      aria-label={label}
      data-align={align}
      className={cn("pointer-events-auto flex h-7 items-center rounded-full border bg-card px-1 text-xs shadow-[var(--shadow)]", className)}
    >
      {children}
    </div>
  );
}

export function PillAction({ children, ...rest }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      role="menuitem"
      className={cn("rounded-full px-2.5 py-1 leading-none whitespace-nowrap hover:bg-accent disabled:opacity-40 disabled:hover:bg-transparent", RING)}
      {...rest}
    >
      {children}
    </button>
  );
}
