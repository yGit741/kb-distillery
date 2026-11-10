import { Link } from "@tanstack/react-router";
import { useMemo } from "react";
import { CopyButton } from "@/components/CopyButton";
import { Button } from "@/components/ui/button";
import { resetAllVariants, useVariant, useVariantChoicesText, VARIANTS, type VariantSpec } from "@/components/variants";
import { tryTargets } from "@/features/proposals/model";
import { useApiQuery } from "@/lib/useApiQuery";
import { cn } from "@/lib/utils";

/** Where each component shows. `page` = a page view (the page with the most open proposals), `proposal` = a review screen. */
export const SHOWN_ON: Record<string, "page" | "proposal" | "/proposals" | "/ingest"> = {
  "page-sources": "page",
  "page-chat-entry": "page",
  "page-flag-mark": "page",
  "page-history-entry": "page",
  "restructure-entry": "page",
  "proposal-diff": "proposal",
  "proposal-inbox": "/proposals",
  "ingest-layout": "/ingest",
};

function tryHref(component: string, t: { page?: string; proposal?: string }): string | null {
  const where = SHOWN_ON[component];
  if (where === "page") return t.page ? `/pages/${encodeURIComponent(t.page)}` : null;
  if (where === "proposal") return t.proposal ? `/proposals/${encodeURIComponent(t.proposal)}` : null;
  return where ?? null;
}

function Component({ id, spec, href }: { id: string; spec: VariantSpec; href: string | null }) {
  const [value, setValue] = useVariant(id, spec.options.map((o) => o.id), spec.default);
  return (
    <section aria-label={spec.label} className="py-5">
      <div className="mb-2 flex items-baseline gap-3">
        <h3 className="text-sm font-medium">{spec.label}</h3>
        <code className="text-xs text-muted-foreground">{id}</code>
        {href && (
          <Link to={href as "/"} className="ml-auto text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline">
            Try it
          </Link>
        )}
      </div>
      <div role="radiogroup" aria-label={spec.label} className="grid gap-1">
        {spec.options.map((o) => {
          const on = o.id === value;
          return (
            <button
              key={o.id}
              type="button"
              role="radio"
              aria-checked={on}
              onClick={() => setValue(o.id)}
              className={cn(
                "flex items-start gap-3 rounded-md border px-3 py-2 text-left transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                on ? "border-primary/40 bg-primary/5" : "border-transparent hover:bg-accent",
              )}
            >
              <span aria-hidden className={cn("mt-[5px] inline-block size-3 shrink-0 rounded-full border", on ? "border-[4px] border-primary" : "border-muted-foreground/50")} />
              <span className="min-w-0 flex-1">
                <span className="text-sm">{o.label}</span>
                {o.id === spec.default && <span className="ml-2 text-xs text-muted-foreground">default</span>}
                <span className="block text-xs text-muted-foreground">{o.hint}</span>
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}

/**
 * System → Variants (flag ui.variant-chooser): every component that ships several designs (the VARIANTS registry),
 * its options with a one-line description, the default marked. A pick applies at once in this browser (the same
 * `kbd.variants.<component>` key the screens read); "Copy choices" gives plain lines to hand to an agent.
 */
export function VariantsView() {
  const q = useApiQuery(["proposals", "list", "open"], (ds) => ds.listProposals("open"), { retry: false });
  const targets = useMemo(() => tryTargets(q.data ?? []), [q.data]);
  const text = useVariantChoicesText();
  return (
    <div className="mx-auto max-w-3xl py-4">
      <div className="flex items-start gap-4" data-tour="variant-chooser">
        <p className="flex-1 text-sm text-muted-foreground">
          Screens with more than one design. Pick one for each; it applies at once, in this browser only. Copy the choices to tell an agent which ones won.
        </p>
        <CopyButton text={text} label="Copy choices" />
        <Button variant="ghost" size="sm" onClick={resetAllVariants}>
          Reset to defaults
        </Button>
      </div>
      <div className="divide-y">
        {Object.entries(VARIANTS).map(([id, spec]) => (
          <Component key={id} id={id} spec={spec} href={tryHref(id, targets)} />
        ))}
      </div>
    </div>
  );
}
