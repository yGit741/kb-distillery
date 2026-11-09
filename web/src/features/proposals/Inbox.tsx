import { Link } from "@tanstack/react-router";
import type { ProposalGroup, ProposalSummary } from "@/api";
import { Empty, ErrorState, Loading } from "@/components/states";
import { useVariant, VARIANTS } from "@/components/variants";
import { useApiQuery } from "@/lib/useApiQuery";
import { cn } from "@/lib/utils";
import { pageTo } from "@/features/pages/parts";
import { useState } from "react";
import { CLASS_HINT, CLASS_ORDER, classLabel, tierMark } from "./model";
import { FeedList } from "./Feed";
import { RebaseButton, Segmented, Tabs } from "./parts";

export const INBOX_COMPONENT = "proposal-inbox";
export const INBOX_LAYOUTS = ["by-page", "by-class", "timeline"] as const;
export type InboxLayout = (typeof INBOX_LAYOUTS)[number];
export const DEFAULT_INBOX_LAYOUT: InboxLayout = "by-page";
const GROUP_OF: Record<InboxLayout, string | undefined> = { "by-page": "page", "by-class": "class", timeline: undefined };
const FILTERS = [
  { id: "open", label: "Open" },
  { id: "applied", label: "Applied" },
  { id: "undone", label: "Undone" },
  { id: "all", label: "All" },
];

export const when = (iso: string) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
};

/** Class chips with counts, riskiest first. */
export function ClassChips({ classes }: { classes: Record<string, number> }) {
  const keys = Object.keys(classes).sort((a, b) => rank(a) - rank(b));
  return (
    <span className="inline-flex flex-wrap items-center gap-1" aria-label="Kinds of change">
      {keys.map((k) => (
        <span key={k} data-chip={k} className="rounded-full border px-1.5 py-px text-xs text-foreground/80">
          {classes[k]} {chipName(k, classes[k] ?? 0)}
        </span>
      ))}
    </span>
  );
}
/** "3 links", "1 link": the class name in the singular when there is one. */
const chipName = (k: string, n: number) => {
  const l = classLabel(k).toLowerCase();
  return n === 1 && l.endsWith("s") && !l.endsWith("ss") ? l.slice(0, -1) : l;
};
const rank = (k: string) => {
  const i = (CLASS_ORDER as readonly string[]).indexOf(k);
  return i < 0 ? CLASS_ORDER.length : i;
};

const TIER_DOT = { explicit: "bg-warn", review: "bg-muted-foreground/50", auto_apply: "bg-ok" } as const;

/** One proposal in a list: title, pages, kinds of change, tier, and a stale badge with Rebase. */
export function ProposalRow({ p, showPages = true }: { p: ProposalSummary; showPages?: boolean }) {
  const tier = tierMark(p.tiers);
  const state = p.status === "stale" ? "open" : p.status;
  return (
    <li className="flex flex-col gap-1.5 py-3" data-testid="proposal-row" data-id={p.id}>
      <div className="flex items-baseline gap-3">
        <Link to={`/proposals/${encodeURIComponent(p.id)}` as "/"} className="min-w-0 truncate font-medium hover:underline">
          {p.title}
        </Link>
        <span className="shrink-0 text-xs text-muted-foreground" data-testid="row-state">{state}</span>
        <span className="ml-auto shrink-0 whitespace-nowrap text-xs text-muted-foreground">{when(p.updated || p.created)}</span>
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-muted-foreground">
        {showPages && <span className="min-w-0 truncate" title={p.pages.join(", ")}>{p.pages.join(", ")}</span>}
        <ClassChips classes={p.classes} />
        <span className="inline-flex items-center gap-1" title={tier.hint} data-testid="tier-mark">
          <span className={cn("size-1.5 rounded-full", TIER_DOT[tier.id])} aria-hidden />
          {tier.label}
        </span>
        {p.stale_pages.length > 0 && (
          <span className="inline-flex items-center gap-2" data-testid="stale-badge">
            <span className="inline-flex items-center gap-1 text-foreground/80" title={p.stale_pages.join(", ")}>
              <span className="size-1.5 rounded-full bg-warn" aria-hidden />
              page changed since
            </span>
            <RebaseButton id={p.id} />
          </span>
        )}
      </div>
    </li>
  );
}

function Section({ title, hint, count, children }: { title: React.ReactNode; hint?: string | undefined; count: number; children: React.ReactNode }) {
  return (
    <section className="flex flex-col">
      <header className="flex items-baseline gap-2 border-b pb-1.5">
        <h2 className="text-sm font-semibold">{title}</h2>
        <span className="text-xs text-muted-foreground">{count}</span>
        {hint && <span className="text-xs text-muted-foreground">{hint}</span>}
      </header>
      <ul className="divide-y">{children}</ul>
    </section>
  );
}

function Groups({ layout, groups, all }: { layout: InboxLayout; groups: ProposalGroup[]; all: ProposalSummary[] }) {
  if (layout === "timeline") {
    return (
      <ul className="divide-y" aria-label="Newest first">
        {all.map((p) => <ProposalRow key={p.id} p={p} />)}
      </ul>
    );
  }
  if (layout === "by-page") {
    return (
      <div className="flex flex-col gap-6">
        {groups.map((g) => (
          <Section key={g.key} title={<Link to={pageTo(g.key)} className="hover:underline">{g.key}</Link>} count={g.count}>
            {g.proposals.map((p) => <ProposalRow key={p.id} p={p} showPages={p.pages.length > 1} />)}
          </Section>
        ))}
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-6">
      {groups.map((g) => (
        <Section key={g.key} title={classLabel(g.key)} hint={CLASS_HINT[g.key]} count={g.count}>
          {g.proposals.map((p) => <ProposalRow key={p.id} p={p} />)}
        </Section>
      ))}
    </div>
  );
}

/** /proposals: what the agent proposed, grouped so twenty link fixes do not bury one changed claim; plus the auto-applied feed. */
export function Inbox() {
  const [layout, setLayout] = useVariant(INBOX_COMPONENT, INBOX_LAYOUTS, DEFAULT_INBOX_LAYOUT);
  const [tab, setTab] = useState("inbox");
  const [status, setStatus] = useState("open");
  const group = GROUP_OF[layout as InboxLayout];
  const q = useApiQuery(["proposals", "inbox", status, group ?? ""], (ds) => ds.getProposalInbox({ status, ...(group ? { group } : {}) }), { enabled: tab === "inbox" });
  const proposals = q.data?.proposals ?? [];
  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-4 px-4 pb-10 pt-6">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Proposals</h1>
          <p className="text-sm text-muted-foreground">What the agent suggests for your pages, and what it applied on its own.</p>
        </div>
        {tab === "inbox" && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            Layout
            <Segmented label="Layout" value={layout} options={(VARIANTS[INBOX_COMPONENT]?.options ?? []).map((o) => ({ id: o.id, label: o.label.toLowerCase(), hint: o.hint }))} onChange={setLayout} />
          </div>
        )}
      </header>
      <Tabs label="Section" value={tab} onChange={setTab} items={[{ id: "inbox", label: "Inbox" }, { id: "feed", label: "Feed", note: "applied by the agent" }]} />
      {tab === "feed" ? (
        <FeedList />
      ) : (
        <>
          <Segmented label="Show" value={status} options={FILTERS} onChange={setStatus} />
          {q.isLoading ? (
            <Loading label="Loading proposals" />
          ) : q.error ? (
            <ErrorState title="Could not load proposals" error={q.error} onRetry={() => void q.refetch()} />
          ) : !proposals.length ? (
            <Empty>{status === "open" ? "Nothing waits for your review." : "No proposals here."}</Empty>
          ) : (
            <Groups layout={layout as InboxLayout} groups={q.data?.groups ?? []} all={proposals} />
          )}
        </>
      )}
    </div>
  );
}
