import { Plus } from "lucide-react";
import { cn } from "@/lib/utils";
import { FAN_FOLDED, FAN_STACK_EDGE, FAN_STACK_SIDE, fanTransform, PILL_W, type FanKind } from "./geometry";
import { useReducedMotion } from "./motion";
import { CardThumb } from "./Thumb";

export interface FanCard {
  key: string;
  title: string;
  /** the small grey text at the pill's right end ("today", "3 notes") */
  meta?: string;
  /** a chat that is running now */
  live?: boolean;
  /** the "New chat" card (flag spark-chat): a plus in place of the picture */
  isNew?: boolean;
}

interface Props {
  kind: FanKind;
  open: boolean;
  /** shown in the group's label for assistive tech: "Think notes", "Chats" */
  label: string;
  cards: readonly FanCard[];
  /** what to say when there are no cards */
  empty: string;
  onPick: (key: string) => void;
}

const RING = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";
const MS = 175; // the mockup's --k (.35) x .5s

/**
 * A fan of cards on one true arc, opening from a corner button like a hand of cards. Agent grows up from the
 * bottom-left; Think is the same arc turned 180 degrees and grows down from the top-right. Each card is a dark
 * picture and a one-line pill; the pill lights up under the pointer. The container takes no pointer events,
 * only the cards do.
 */
export function Fan({ kind, open, label, cards, empty, onPick }: Props) {
  const agent = kind === "agent";
  const still = useReducedMotion();
  const shown: FanCard[] = cards.length ? [...cards] : [{ key: "", title: empty }];
  return (
    <div
      role="group"
      aria-label={label}
      aria-hidden={!open}
      inert={!open}
      data-fan={kind}
      data-open={open}
      className="pointer-events-none absolute z-[25]"
      style={agent ? { left: FAN_STACK_SIDE, bottom: FAN_STACK_EDGE } : { right: FAN_STACK_SIDE, top: FAN_STACK_EDGE }}
    >
      {shown.map((c, i) => {
        const none = !c.key;
        return (
          <button
            key={c.key || "none"}
            type="button"
            disabled={none}
            title={none ? undefined : c.title}
            aria-label={none ? undefined : `${c.title}${c.meta ? `, ${c.meta}` : ""}`}
            onClick={() => onPick(c.key)}
            data-card={i}
            className={cn(
              "group pointer-events-auto absolute flex items-center gap-2 whitespace-nowrap rounded-[10px] text-left motion-reduce:transition-none",
              agent ? "bottom-0 left-0" : "right-0 top-0 flex-row-reverse",
              RING,
            )}
            style={{
              transformOrigin: agent ? "36px calc(100% - 25px)" : "calc(100% - 36px) 25px",
              transform: open ? fanTransform(kind, i) : FAN_FOLDED,
              opacity: open ? 1 : 0,
              transition: still ? "none" : `transform ${MS}ms cubic-bezier(.32,.72,0,1) ${open ? i * 20 : (shown.length - i) * 10}ms, opacity ${MS / 2}ms ease ${open ? i * 20 : 0}ms`,
            }}
          >
            {c.isNew ? (
              <span aria-hidden className="grid h-[50px] w-[72px] flex-none place-items-center rounded-[7px] border bg-card text-muted-foreground shadow-[var(--shadow)]">
                <Plus className="size-5" strokeWidth={1.6} />
              </span>
            ) : (
              <CardThumb accent={kind === "think" ? "warn" : "primary"} />
            )}
            {c.live && <span className="absolute top-1/2 size-[7px] -translate-y-1/2 rounded-full bg-ok" style={agent ? { left: 76 } : { right: 76 }} aria-hidden />}
            <span
              className={cn(
                "flex h-[26px] items-center overflow-hidden rounded-full bg-card px-3 text-[13px] shadow-[var(--shadow)] transition-colors duration-150",
                none ? "text-muted-foreground" : "group-hover:bg-primary group-hover:text-primary-foreground group-focus-visible:bg-primary group-focus-visible:text-primary-foreground",
              )}
              style={{ width: PILL_W }}
            >
              <span className="min-w-0 flex-1 truncate">{c.title}</span>
              {c.meta && <small className="ml-2 flex-none text-[11px] opacity-60">{c.meta}</small>}
            </span>
          </button>
        );
      })}
    </div>
  );
}
