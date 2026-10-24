import { useNavigate } from "@tanstack/react-router";
import { useEffect, useLayoutEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { activeTour, markSeen, type TourStep } from "./tours";

interface Rect {
  top: number;
  left: number;
  width: number;
  height: number;
}

const rectOf = (anchor: string): Rect | null => {
  const el = document.querySelector(`[data-tour="${CSS.escape(anchor)}"]`);
  if (!el) return null;
  const r = el.getBoundingClientRect();
  return { top: r.top, left: r.left, width: r.width, height: r.height };
};

/**
 * The tour overlay: a ring around the current step's element and a small card under it with Next / Skip.
 * Esc skips. Steps whose element is missing are skipped, so a tour never points at nothing. Mounted once
 * in AppShell; renders nothing unless the build named a tour that this visitor has not finished.
 */
export function Tour({ id, tours }: { id: string | null | undefined; tours?: Record<string, readonly TourStep[]> }) {
  const [steps] = useState(() => activeTour(id, tours));
  const [i, setI] = useState(0);
  const [rect, setRect] = useState<Rect | null>(null);
  const navigate = useNavigate();
  const step = steps[i];

  const finish = () => {
    if (id) markSeen(id);
    setI(steps.length);
  };

  useEffect(() => {
    if (step?.route) void navigate({ to: step.route as "/" });
  }, [step, navigate]);

  useLayoutEffect(() => {
    if (!step) return;
    let tries = 0;
    const t = setInterval(() => {
      const r = rectOf(step.anchor);
      if (r || ++tries > 20) {
        clearInterval(t);
        if (r) setRect(r);
        else setI((n) => n + 1); // element never appeared: skip the step
      }
    }, 100);
    return () => clearInterval(t);
  }, [step]);

  useEffect(() => {
    if (!step) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && finish();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  if (!step || !rect) return null;
  const last = i === steps.length - 1;
  const below = rect.top + rect.height + 12;
  const cardTop = below + 160 > window.innerHeight ? Math.max(8, rect.top - 172) : below;
  return (
    <div className="pointer-events-none fixed inset-0 z-[60]" role="dialog" aria-label={`Tour step ${i + 1} of ${steps.length}`}>
      <div
        className="absolute rounded-lg ring-4 ring-primary/70 shadow-[0_0_0_9999px_rgba(0,0,0,0.35)]"
        style={{ top: rect.top - 4, left: rect.left - 4, width: rect.width + 8, height: rect.height + 8 }}
      />
      <div
        className="pointer-events-auto absolute w-[min(20rem,calc(100vw-2rem))] rounded-xl border bg-card p-4 text-card-foreground shadow-[var(--shadow)]"
        style={{ top: cardTop, left: Math.min(Math.max(16, rect.left), window.innerWidth - 336) }}
      >
        <p className="text-xs text-muted-foreground">
          {i + 1} / {steps.length}
        </p>
        <h2 className="mt-1 text-sm font-semibold">{step.title}</h2>
        <p className="mt-1 text-sm text-muted-foreground">{step.body}</p>
        <div className="mt-3 flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={finish}>
            Skip
          </Button>
          <Button size="sm" onClick={() => (last ? finish() : (setRect(null), setI(i + 1)))}>
            {last ? "Done" : "Next"}
          </Button>
        </div>
      </div>
    </div>
  );
}
