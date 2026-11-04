import { useState } from "react";
import { BookOpen, ChevronDown, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { StartScreen } from "@/features/start/StartScreen";

const KEY = "home.start-card.dismissed";

function readDismissed(): boolean {
  try {
    return localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

/** The old Start screen, folded into Home: a one-line card that opens the guide in place, dismissable for good. */
export function StartCard({ open: openInitially = false }: { open?: boolean }) {
  const [dismissed, setDismissed] = useState(() => !openInitially && readDismissed());
  const [open, setOpen] = useState(openInitially);
  if (dismissed) return null;
  const dismiss = () => {
    try {
      localStorage.setItem(KEY, "1");
    } catch {
      // private window: the card just comes back next time
    }
    setDismissed(true);
  };
  return (
    <Card className="mx-auto mb-3 w-full min-w-0 max-w-[1100px] px-4 py-3 sm:px-5" aria-label="Start here" data-testid="start-card">
      <div className="flex items-center gap-3">
        <BookOpen className="size-4 shrink-0 text-muted-foreground" aria-hidden />
        <p className="min-w-0 flex-1 text-sm">
          <b>Start here</b>
          <span className="text-muted-foreground"> — how to add and edit knowledge, and how to build a feature.</span>
        </p>
        <Button variant="ghost" size="sm" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          {open ? "Hide guide" : "Open guide"}
          <ChevronDown className={open ? "size-4 rotate-180" : "size-4"} aria-hidden />
        </Button>
        <Button variant="ghost" size="icon" aria-label="Dismiss the start card" onClick={dismiss}>
          <X className="size-4" aria-hidden />
        </Button>
      </div>
      {open && (
        <div className="mt-3 border-t pt-3">
          <StartScreen />
        </div>
      )}
    </Card>
  );
}
