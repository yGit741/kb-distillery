import { Library } from "lucide-react";
import type { ReactNode } from "react";
import { AddSources } from "@/components/AddSources";

/** Where the example action goes (it falls back to Start). */
export interface FirstRunHost {
  go: (to: string, search?: Record<string, string>) => void;
  href: (to: string, search?: Record<string, string>) => string;
}

function Action({ icon, title, hint, onClick, href }: { icon: ReactNode; title: string; hint: string; onClick: () => void; href: string }) {
  return (
    <a
      href={href}
      onClick={(e) => {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
        e.preventDefault();
        onClick();
      }}
      className="flex items-center gap-3 rounded-lg border bg-background px-4 py-3 text-left transition-colors hover:bg-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring"
    >
      <span className="text-muted-foreground [&_svg]:size-5">{icon}</span>
      <span className="flex flex-col">
        <span className="text-sm font-medium text-foreground">{title}</span>
        <span className="text-xs text-muted-foreground">{hint}</span>
      </span>
    </a>
  );
}

/** Calm first-run card for a knowledge base with no pages yet (flag screen.first-run). */
export function FirstRunCard({ host }: { host: FirstRunHost }) {
  const start = { start: "true" };
  return (
    <div className="flex h-full min-h-[24rem] items-center justify-center p-4" data-testid="first-run">
      <section aria-labelledby="first-run-title" className="w-full max-w-md rounded-xl border bg-card p-6 shadow-sm">
        <h2 id="first-run-title" className="text-lg font-semibold text-foreground">Build your knowledge base</h2>
        <p className="mt-1 text-sm text-muted-foreground">Add some sources and the graph fills in as they are digested.</p>
        <div className="mt-5 flex flex-col gap-4">
          <AddSources />
          <Action icon={<Library />} title="Open an example knowledge base" hint="See how a finished one looks" onClick={() => host.go("/", start)} href={host.href("/", start)} />
        </div>
      </section>
    </div>
  );
}
