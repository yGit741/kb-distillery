import { Link } from "@tanstack/react-router";
import { FileText, Layers, Undo2 } from "lucide-react";
import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { pageTo } from "@/features/pages/parts";
import { MarkedText, Tokens, WhyLine } from "@/features/proposals/parts";
import { cn } from "@/lib/utils";
import type { Card } from "./api";
import { classLabel, plural, sourceLabel, wordDiff } from "./model";

const PRODUCER: Record<string, string> = { ingest: "ingest", chat: "page chat", flags: "flag fix", lint: "nightly lint", restructure: "restructure", restore: "restore", manual: "agent" };

/** What a card is about, said as facts the owner can check (never a score). */
export function signals(c: Card): { text: string; tone: "bad" | "warn" | "muted" }[] {
  const out: { text: string; tone: "bad" | "warn" | "muted" }[] = [];
  for (const f of c.findings) out.push({ text: f.message, tone: f.severity === "error" ? "bad" : f.severity === "warning" ? "warn" : "muted" });
  const cites = (s: string) => (s.match(/\[\^[^\]]+\]/g) ?? []).length;
  if (c.hunk.op === "edit_page" && cites(c.hunk.after) < cites(c.hunk.before)) out.push({ text: "removes a citation", tone: "warn" });
  if ((c.klass === "claims" || c.klass === "new_page") && !c.hunk.sources.length && !cites(c.hunk.after)) out.push({ text: "no source", tone: "warn" });
  if (c.stale) out.push({ text: "the page changed since: rebase before applying", tone: "warn" });
  return out;
}

const TONE = { bad: "text-bad", warn: "text-warn", muted: "text-muted-foreground" };

/** The frontmatter fields a new page shows above its body. */
function fields(text: string): { title: string; description: string; type: string; body: string; sources: string[] } {
  const m = /^---\n([\s\S]*?)\n---\n?/.exec(text);
  const fm = m?.[1] ?? "";
  const get = (k: string) => new RegExp(`^${k}:\\s*(.+)$`, "m").exec(fm)?.[1]?.replace(/^["']|["']$/g, "").trim() ?? "";
  const sources = [...fm.matchAll(/^\s*-\s*id:\s*(.+)$/gm)].map((x) => x[1]!.trim());
  return { title: get("title"), description: get("description"), type: get("type"), body: text.slice(m?.[0].length ?? 0).trim(), sources };
}

function Context({ text, expanded }: { text: string; expanded: boolean }) {
  if (!text) return null;
  return <p className={cn("whitespace-pre-wrap break-words text-[15px] leading-7 text-muted-foreground/70", !expanded && "line-clamp-3")}>{text}</p>;
}

export interface Revised {
  /** the card this note belongs to */
  cardId: string;
  version: number;
  instruction: string;
  reply: string;
  /** the proposed text before the rewrite (for "vs v1") */
  prevAfter: string;
}

export function ChangeCard({ card, position, expanded, revised, vsPrev, onVsPrev, onBack, children }: {
  card: Card;
  position: string;
  expanded: boolean;
  revised: Revised | null;
  vsPrev: boolean;
  onVsPrev: (on: boolean) => void;
  onBack: (() => void) | null;
  children?: ReactNode;
}) {
  const h = card.hunk;
  const isNew = h.op === "create_page";
  const page = isNew ? fields(h.after) : null;
  const flags = signals(card);
  const meta = [classLabel(card.klass), PRODUCER[card.producer] ?? card.producer, card.source ? sourceLabel(card.source) : ""].filter(Boolean);
  return (
    <article className="flex flex-col gap-4" data-tour="review-card" aria-label={`${classLabel(card.klass)} on ${card.page_title}`}>
      <header className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
        <Link to={pageTo(h.slug)} className="font-medium text-foreground hover:underline">{card.page_title || h.slug}</Link>
        <span aria-hidden>·</span>
        <span>{meta.join(" · ")}</span>
        <span className="ml-auto tabular-nums" data-tour="review-progress">{position}</span>
      </header>

      {revised && (
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground" role="status">
          <Badge variant="primary">v{revised.version}</Badge>
          <span className="italic">“{revised.instruction}”</span>
          {revised.reply && <span>· {revised.reply}</span>}
          <span className="ml-auto flex items-center gap-1">
            <button type="button" className={cn("rounded px-1.5 py-0.5 hover:bg-accent", vsPrev && "bg-muted text-foreground")} aria-pressed={vsPrev} onClick={() => onVsPrev(!vsPrev)}>
              vs v{revised.version - 1}
            </button>
            {onBack && (
              <button type="button" className="flex items-center gap-1 rounded px-1.5 py-0.5 hover:bg-accent" onClick={onBack}>
                <Undo2 className="size-3" aria-hidden /> Back to v{revised.version - 1}
              </button>
            )}
          </span>
        </div>
      )}

      {isNew && page ? (
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="ok">new page</Badge>
            {page.type && <Badge variant="outline">{page.type}</Badge>}
          </div>
          <h2 className="text-xl font-semibold leading-tight">{page.title || h.slug}</h2>
          {page.description && <p className="text-[15px] leading-7 text-muted-foreground">{page.description}</p>}
          <div className={cn("whitespace-pre-wrap break-words text-[16px] leading-7", !expanded && "line-clamp-[12]")}>
            {revised && vsPrev ? <Tokens tokens={wordDiff(fields(revised.prevAfter).body, page.body)} /> : page.body}
          </div>
          {page.sources.length > 0 && <p className="text-xs text-muted-foreground">sources: {page.sources.join(", ")}</p>}
        </div>
      ) : (
        <div className="flex max-w-[68ch] flex-col gap-3">
          <Context text={card.context_before} expanded={expanded} />
          <div className="border-l-2 border-primary/50 pl-3 text-[16px]">
            {h.op === "tombstone_page" ? (
              <p className="leading-7">Retire <span className="font-medium">{card.page_title}</span>: {h.after.replace(/^tombstone \S+ -> /, "its readers are sent to ")}</p>
            ) : revised && vsPrev ? (
              <div className="whitespace-pre-wrap break-words leading-7"><Tokens tokens={wordDiff(revised.prevAfter.trim(), h.after.trim())} /></div>
            ) : (
              <MarkedText hunk={h} className={cn(!expanded && "max-h-[50vh] overflow-y-auto")} />
            )}
          </div>
          <Context text={card.context_after} expanded={expanded} />
        </div>
      )}

      <div data-tour="review-why">
        <WhyLine hunk={h} />
        {flags.length > 0 && (
          <ul className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs" aria-label="Things to check">
            {flags.map((f) => (
              <li key={f.text} className={TONE[f.tone]}>{f.text}</li>
            ))}
          </ul>
        )}
        {expanded && (
          <Link to={pageTo(h.slug)} search={{ review: card.proposal_id } as never} className="mt-1 inline-block text-xs text-primary hover:underline">
            Open the whole change in the page
          </Link>
        )}
      </div>
      {children}
    </article>
  );
}

export function StackCard({ klass, cards, position }: { klass: string; cards: Card[]; position: string }) {
  return (
    <article className="flex flex-col gap-3" data-tour="review-card" aria-label={`${plural(cards.length, classLabel(klass))}`}>
      <header className="flex items-center gap-2 text-xs text-muted-foreground">
        <Layers className="size-4" aria-hidden />
        <span>low-risk changes, one decision for all</span>
        <span className="ml-auto tabular-nums" data-tour="review-progress">{position}</span>
      </header>
      <h2 className="text-xl font-semibold">{plural(cards.length, classLabel(klass))}</h2>
      <ul className="flex flex-col gap-1.5 text-sm">
        {cards.slice(0, 6).map((c) => (
          <li key={c.id} className="flex gap-2">
            <span className="w-36 shrink-0 truncate text-muted-foreground">{c.page_title}</span>
            <span className="min-w-0 truncate"><Tokens tokens={c.hunk.tokens} /></span>
          </li>
        ))}
        {cards.length > 6 && <li className="text-muted-foreground">and {cards.length - 6} more</li>}
      </ul>
      <p className="text-xs text-muted-foreground">Accept or reject them all, or open the stack to go one by one (O).</p>
    </article>
  );
}

export function CoverCard({ source, newPages, changes, position }: { source: string; newPages: number; changes: number; position: string }) {
  const parts = [newPages ? plural(newPages, "new page") : "", changes ? plural(changes, "change to existing pages", "changes to existing pages") : ""].filter(Boolean);
  return (
    <article className="flex flex-col gap-3" data-tour="review-cover" aria-label={`What ${sourceLabel(source)} would add`}>
      <header className="flex items-center gap-2 text-xs text-muted-foreground">
        <FileText className="size-4" aria-hidden />
        <span>a source you added</span>
        <span className="ml-auto tabular-nums" data-tour="review-progress">{position}</span>
      </header>
      <h2 className="break-all text-xl font-semibold">{sourceLabel(source)}</h2>
      <p className="text-[15px] leading-7">The agent read it and would add {parts.join(" and ") || "nothing"}. The file itself stays untouched in raw/.</p>
      <p className="text-xs text-muted-foreground">Review its cards now, or leave the whole source for later.</p>
    </article>
  );
}
