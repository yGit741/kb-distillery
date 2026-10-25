import { Check, Route } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { listTours, runTour } from "@/features/tour/tours";

/**
 * The Tours menu: every registered tour with a summary (the Home → Graph journeys), a tick on the ones this
 * browser has finished. Picking one starts it; the list is read when the menu opens, so ticks stay current.
 */
export function ToursMenu() {
  const [open, setOpen] = useState(false);
  const tours = useMemo(() => (open ? listTours().filter((t) => t.summary) : []), [open]);
  return (
    <div className="relative shrink-0">
      <Button variant="outline" size="sm" aria-label="Tours" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)} onKeyDown={(e) => e.key === "Escape" && setOpen(false)}>
        <Route aria-hidden />
        <span className="hidden sm:inline">Tours</span>
      </Button>
      {open && (
        <ul role="menu" aria-label="Tours" className="absolute right-0 top-full z-30 mt-1 w-80 rounded-lg border bg-popover p-1 text-sm shadow-[var(--shadow)]">
          {tours.map((t) => (
            <li key={t.name} role="none">
              <button
                type="button"
                role="menuitem"
                className="flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left hover:bg-accent"
                onClick={() => {
                  setOpen(false);
                  runTour(t.name);
                }}
              >
                <span className="min-w-0 flex-1">
                  <span className="block font-medium">{t.name}</span>
                  <span className="block text-xs text-muted-foreground">{t.summary}</span>
                </span>
                {t.seen && <Check aria-label="seen" className="mt-0.5 size-4 shrink-0 text-muted-foreground" />}
              </button>
            </li>
          ))}
          {tours.length === 0 && <li className="px-2 py-1.5 text-xs text-muted-foreground">No tours yet.</li>}
        </ul>
      )}
    </div>
  );
}
