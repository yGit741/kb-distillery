import { cn } from "@/lib/utils";
import type { GraphSubject } from "../../colourDimensions";
import { SUBJECTS } from "../../subject";

const RING = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

/**
 * Concepts / Sources (flag graph-intent): a quiet two-way switch just above the page types, at the bottom centre.
 * It says what the graph is about; the legends under and beside it follow.
 */
export function SubjectToggle({ subject, onPick }: { subject: GraphSubject; onPick: (s: GraphSubject) => void }) {
  return (
    <div
      role="radiogroup"
      aria-label="What the graph shows"
      data-corners="subject"
      data-tour="graph-subject"
      className="pointer-events-auto absolute bottom-[38px] left-1/2 z-[24] flex -translate-x-1/2 items-center gap-0.5 rounded-full bg-card/90 p-0.5 shadow-[var(--shadow)] [.gt-active_&]:bottom-[110px]"
    >
      {SUBJECTS.map((s) => (
        <button
          key={s.id}
          type="button"
          role="radio"
          aria-checked={subject === s.id}
          title={s.hint}
          onClick={() => onPick(s.id)}
          className={cn("rounded-full px-2.5 py-0.5 text-[12px] leading-5 transition-colors motion-reduce:transition-none", subject === s.id ? "bg-accent text-foreground" : "text-muted-foreground hover:text-foreground", RING)}
        >
          {s.label}
        </button>
      ))}
    </div>
  );
}
