import { useState, type ComponentType, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useFlag } from "@/flags/useFlag";
import { modules } from "@/routes/modules";

type Guide = ComponentType<{ heading?: "h1" | "h2"; actions?: ReactNode }>;

/**
 * The guide comes from the Start feature module as the build lists it (routes/modules, swapped per share profile),
 * never by a direct import: a public snapshot does not carry that screen at all, so it has no card either.
 * Read at render time because this file is itself imported by a screen module.
 */
const startGuide = (): Guide | undefined =>
  (Object.entries(modules).find(([file]) => file.endsWith("/features/start/index.tsx"))?.[1] as { StartGuide?: Guide } | undefined)?.StartGuide;

export const START_DISMISSED_KEY = "kb.home.start-dismissed";

/** Browser-side convenience only: a private window or blocked storage throws, and the card then just shows again next visit. */
function readDismissed(): boolean {
  try {
    return window.localStorage.getItem(START_DISMISSED_KEY) === "1";
  } catch {
    return false;
  }
}
function saveDismissed(): void {
  try {
    window.localStorage.setItem(START_DISMISSED_KEY, "1");
  } catch {
    /* the card stays dismissed for this visit only */
  }
}

/**
 * The "Start here" card at the top of Home (flag screen.start). Dismiss hides it and remembers that; `forced`
 * (the `?start` link, which `/start` redirects to) shows it again even when dismissed. `onDismissed` lets the
 * host drop the `start` param so the card does not come back while the link is still in the address bar.
 */
export function StartCard({ forced = false, onDismissed }: { forced?: boolean; onDismissed?: () => void }) {
  const on = useFlag("screen.start");
  const [dismissed, setDismissed] = useState(readDismissed);
  const StartGuide = startGuide();
  if (!on || !StartGuide || (dismissed && !forced)) return null;
  const dismiss = () => {
    saveDismissed();
    setDismissed(true);
    onDismissed?.();
  };
  return (
    <Card className="mx-auto mb-4 w-full min-w-0 max-w-[1100px] px-4 pb-5 pt-4 sm:px-5" data-testid="start-card">
      <StartGuide
        heading="h2"
        actions={
          <Button variant="ghost" size="sm" className="shrink-0" onClick={dismiss}>
            Dismiss
          </Button>
        }
      />
    </Card>
  );
}
