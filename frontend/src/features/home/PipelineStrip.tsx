import { ExternalLink } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useDataSource, type RawCard } from "@/api";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { useApiQuery } from "@/lib/useApiQuery";
import { cn } from "@/lib/utils";
import { NodeMarkSvg, ShapeIcon } from "@/features/graph/encoding";
import type { GNode } from "@/features/graph/types";
import { ConceptDots, DepthSwatch, Dot, KIND_ICON, RAW_COLOR, StageArrow } from "./glossary";
import { conceptsFed, type SourceDraw, type Vault } from "./samplers";

/** Chips the "Concepts it feeds" stage shows before "+ N more". */
export const FED_MAX = 4;
/** Every stage's fixed height in px: the same on every draw, whatever the source. */
export const STAGE_HEIGHT = 172;
/** Areas the Source stage lists before "+N". */
export const AREAS_MAX = 2;

/** "Abbe, Boix" stays; three or more authors become "Abbe et al." (the first author's family name). */
export function shortAuthors(s: string): string {
  const names = s
    .replace(/^\[|\]$/g, "")
    .split(/\s*(?:,|;|\band\b|&)\s*/)
    .map((x) => x.replace(/^["']|["']$/g, "").trim())
    .filter(Boolean);
  if (names.length <= 2) return names.join(", ");
  const first = names[0]!.split(/\s+/);
  return `${first[first.length - 1]} et al.`;
}

/** The first AREAS_MAX areas and "+N" for the rest. */
export function shortAreas(areas: readonly string[]): string {
  const head = areas.slice(0, AREAS_MAX).join(" · ");
  return areas.length > AREAS_MAX ? `${head} +${areas.length - AREAS_MAX}` : head;
}

const props = (n: GNode) => (n.properties ?? {}) as Record<string, unknown>;
const prop = (n: GNode, k: string) => {
  const v = props(n)[k];
  return v == null || v === "" ? "" : String(v);
};
/** The first raw/… file of a source page, or null (public builds drop `raw`). */
export function rawPathOf(n: GNode): string | null {
  return (
    prop(n, "raw")
      .replace(/[[\]]/g, "")
      .split(",")
      .map((s) => s.trim())
      .find((s) => s.startsWith("raw/")) ?? null
  );
}

export function formatBytes(n: number | null | undefined): string {
  if (n == null) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

const KIND_LABEL: Record<string, string> = {
  pdf: "PDF",
  handwritten: "Handwritten PDF",
  slides: "Slides",
  chat: "LLM chat",
  email: "Email",
  web: "Web clip",
  youtube: "YouTube",
  image: "Image",
  other: "File",
};

function Stage({ title, dots, children, className }: { title: string; dots: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={cn("flex min-w-0 flex-col gap-1.5 overflow-hidden rounded-lg border bg-muted/40 px-2.5 py-2", className)} style={{ height: STAGE_HEIGHT }} data-stage={title}>
      <h3 className="flex items-center gap-1.5 text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">
        {dots}
        {title}
      </h3>
      {children}
    </div>
  );
}

/** The small square on a stage: a real thumbnail, or a kind-specific stand-in. */
function Mini({ onClick, label, children, className }: { onClick: () => void; label: string; children: ReactNode; className?: string }) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      className={cn(
        "flex aspect-[1/1.25] w-[72px] shrink-0 flex-col overflow-hidden rounded-[3px] border bg-card text-left outline-none hover:ring-2 hover:ring-primary focus-visible:ring-2 focus-visible:ring-ring",
        className,
      )}
    >
      {children}
    </button>
  );
}

function thumbSrc(card: RawCard | undefined, path: string | null, width: number, ds: ReturnType<typeof useDataSource>): string | null {
  if (!card) return null;
  if (card.thumb) return card.thumb;
  if (card.has_thumb && path) return ds.rawThumbUrl(path, width);
  if (card.kind === "youtube" && card.video_id) return `https://img.youtube.com/vi/${card.video_id}/mqdefault.jpg`;
  return null;
}

function RawStage({ source }: { source: GNode }) {
  const ds = useDataSource();
  const path = rawPathOf(source);
  const q = useApiQuery(["raw-card", source.id, path], (d) => d.getRawCard(source.id, path), { retry: false, staleTime: 5 * 60_000 });
  const [open, setOpen] = useState(false);
  const card = q.data;
  const kind = card?.kind ?? (path?.endsWith(".pdf") ? "pdf" : "other");
  const Icon = KIND_ICON[kind] ?? KIND_ICON.other!;
  const fmt = card?.format ?? path?.split("/")[1] ?? null;
  const src = thumbSrc(card, path, 240, ds);
  const name = card?.name ?? card?.title ?? (fmt ? `A file in raw/${fmt}` : "The original file");
  const facts = [KIND_LABEL[kind] ?? "File", card?.facts.pages ? `${card.facts.pages} pages` : "", card?.kind === "chat" && card.turn_count ? `${card.turn_count} turns` : "", formatBytes(card?.facts.bytes)]
    .filter(Boolean)
    .join(" · ");
  return (
    <Stage title="Raw" dots={<Dot color={RAW_COLOR} />}>
      <b title={name} className="line-clamp-2 h-[2.75em] shrink-0 text-[12.5px] font-semibold leading-snug [overflow-wrap:anywhere]">{name}</b>
      <div className="flex items-stretch gap-2">
        <Mini label={`Preview ${name}`} onClick={() => setOpen(true)}>
          {src ? (
            <img src={src} alt="" className="h-full w-full object-cover object-top" />
          ) : card?.kind === "chat" && card.turns.length ? (
            <span className="flex flex-col gap-0.5 p-1 text-[5.5px] leading-tight">
              {card.turns.slice(0, 3).map((t, i) => (
                <span key={i} className={cn("line-clamp-3 rounded px-1 py-0.5", t.role === "user" ? "ml-2 bg-primary/15" : "mr-2 bg-muted")}>
                  {t.text}
                </span>
              ))}
            </span>
          ) : card?.excerpt ? (
            <span className="line-clamp-[12] p-1 font-mono text-[5.5px] leading-tight text-foreground">{card.excerpt}</span>
          ) : (
            <span className="m-auto text-muted-foreground">
              <Icon aria-hidden className="size-6" />
            </span>
          )}
        </Mini>
        <div className="flex min-w-0 flex-col justify-center gap-0.5 whitespace-nowrap text-[11px] text-muted-foreground [&>span]:truncate">
          {fmt && (
            <span className="flex items-center gap-1">
              <Icon aria-hidden className="size-3.5 shrink-0" /> <span className="truncate">raw/{fmt}</span>
            </span>
          )}
          {facts && <span>{facts}</span>}
          {card?.model && <span>{card.model}</span>}
          {card?.site && kind !== "chat" && <span>{card.site}</span>}
          {card?.facts.added && <span>added {card.facts.added}</span>}
          <span>immutable</span>
        </div>
      </div>
      <RawPreviewDialog open={open} onOpenChange={setOpen} source={source} card={card} path={path} name={name} src={thumbSrc(card, path, 640, ds) ?? src} />
    </Stage>
  );
}

function RawPreviewDialog({
  open,
  onOpenChange,
  source,
  card,
  path,
  name,
  src,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  source: GNode;
  card: RawCard | undefined;
  path: string | null;
  name: string;
  src: string | null;
}) {
  const ds = useDataSource();
  const file = path && card ? ds.rawFileUrl(path) : null;
  const original = card?.url || prop(source, "url") || null;
  const kind = card?.kind ?? "other";
  const visual = ["pdf", "handwritten", "slides", "image", "youtube"].includes(kind) && src;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="top-[8%] max-w-xl">
        <div className="flex max-h-[80vh] flex-col gap-3 overflow-y-auto p-4">
          <DialogTitle className="pr-6 text-sm font-semibold [overflow-wrap:anywhere]">
            {KIND_LABEL[kind] ?? "File"}
            {kind === "pdf" || kind === "handwritten" || kind === "slides" ? " · page 1" : ""} — {name}
          </DialogTitle>
          <DialogDescription className="sr-only">Preview of the raw file behind {source.title || source.id}</DialogDescription>
          {visual ? (
            <img src={src} alt={`First page of ${name}`} className="mx-auto max-h-[60vh] rounded border bg-white" />
          ) : kind === "chat" && card?.turns.length ? (
            <ol className="flex flex-col gap-2 text-sm">
              {card.turns.map((t, i) => (
                <li key={i} className={cn("max-w-[85%] rounded-lg px-3 py-2", t.role === "user" ? "self-end bg-primary/15" : "self-start bg-muted")}>
                  <span className="mb-0.5 block text-[10px] uppercase tracking-wider text-muted-foreground">{t.role === "user" ? "Me" : card.model || "Model"}</span>
                  {t.text}
                </li>
              ))}
            </ol>
          ) : kind === "email" && card?.header ? (
            <div className="text-sm">
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 text-xs">
                <dt className="text-muted-foreground">From</dt>
                <dd>{card.header.sender}</dd>
                <dt className="text-muted-foreground">Date</dt>
                <dd>{card.header.date}</dd>
                <dt className="text-muted-foreground">Subject</dt>
                <dd>{card.header.subject}</dd>
              </dl>
              {card.excerpt && <p className="mt-2 line-clamp-3 text-muted-foreground">{card.excerpt}</p>}
            </div>
          ) : card?.excerpt ? (
            <div className="text-sm">
              {card.title && <p className="font-semibold">{card.title}</p>}
              {card.site && <p className="text-xs text-muted-foreground">{card.site}</p>}
              <p className="mt-2 whitespace-pre-line leading-relaxed">{card.excerpt}</p>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              {card ? "Only the facts of this file are shared here." : "The raw file stays in the private vault; this view has its facts only."}
            </p>
          )}
          <p className="flex flex-wrap gap-3 text-xs text-muted-foreground">
            {!file && visual && <span>Page 1 rendered at build time; the full file stays in the private vault.</span>}
            {file && (
              <a className="inline-flex items-center gap-1 text-primary hover:underline" href={file} target="_blank" rel="noopener noreferrer">
                Open {kind === "pdf" || kind === "handwritten" || kind === "slides" ? "PDF" : "file"} <ExternalLink aria-hidden className="size-3" />
              </a>
            )}
            {original && (
              <a className="inline-flex items-center gap-1 text-primary hover:underline" href={original} target="_blank" rel="noopener noreferrer">
                Original <ExternalLink aria-hidden className="size-3" />
              </a>
            )}
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function SourceStage({ source, onRead }: { source: GNode; onRead: (slug: string) => void }) {
  const authors = shortAuthors(prop(source, "authors") || prop(source, "author"));
  const venue = prop(source, "source") || prop(source, "venue");
  const byline = [authors, [venue, source.year && !venue.includes(String(source.year)) ? source.year : ""].filter(Boolean).join(" ")].filter(Boolean).join(" · ");
  const out = Number(prop(source, "links_out") || source.outDegree || 0);
  const inn = Number(prop(source, "links_in") || source.inDegree || 0);
  return (
    <Stage title="Source" dots={<NodeMarkSvg type={source.type} className="size-3.5 text-muted-foreground" />}>
      <b title={source.title || source.id} className="line-clamp-2 h-[2.75em] shrink-0 text-[12.5px] font-semibold leading-snug [overflow-wrap:anywhere]">{source.title || source.id}</b>
      <div className="flex items-stretch gap-2">
        <Mini label={`Read ${source.title || source.id}`} onClick={() => onRead(source.id)} className="bg-muted/60">
          <span className="whitespace-pre p-1 font-mono text-[6px] leading-[1.2] text-foreground">
            {`---\ntype: ${source.type}\nlayer: source\n${source.year ? `year: ${source.year}\n` : ""}depth: ${source.depth}\n---\n# ${(source.title || source.id).split(/\s+/).slice(0, 6).join("\n")}`}
          </span>
        </Mini>
        <div className="flex min-w-0 flex-col justify-center gap-0.5 whitespace-nowrap text-[11px] text-muted-foreground [&>span]:truncate">
          {byline && <span title={byline}>{byline}</span>}
          <span className="flex items-center gap-1">
            <DepthSwatch depth={source.depth} /> {source.depth || "listed"}
          </span>
          {source.areas.length > 0 && <span title={source.areas.join(" · ")}>{shortAreas(source.areas)}</span>}
          <span>
            {out} links out · {inn} in
          </span>
        </div>
      </div>
    </Stage>
  );
}

function ConceptsStage({ vault, source, concept, onPick }: { vault: Vault; source: string; concept: string; onPick: (id: string) => void }) {
  const fed = conceptsFed(vault, source, concept);
  const shown = fed.slice(0, FED_MAX);
  // a topic and an idea can share a title: name the type next to any title that repeats
  const titles = shown.map((id) => (vault.byId.get(id)!.title || id).toLowerCase());
  const repeats = (id: string) => titles.filter((t) => t === (vault.byId.get(id)!.title || id).toLowerCase()).length > 1;
  return (
    <Stage title="Concepts it feeds" dots={<ConceptDots />}>
      <ul className="flex flex-col gap-1">
        {shown.map((id) => {
          const n = vault.byId.get(id)!;
          const hit = id === concept;
          return (
            <li key={id} className="min-w-0">
              <button
                type="button"
                onClick={() => onPick(id)}
                title={`${n.type}: ${n.title || id}`}
                aria-label={`Pick ${n.type} ${n.title || id}`}
                aria-current={hit || undefined}
                className={cn(
                  "inline-flex max-w-full items-center gap-1.5 rounded-md border bg-card px-2 py-0.5 text-xs hover:border-primary",
                  hit ? "border-primary font-semibold ring-2 ring-primary/25" : "opacity-70 hover:opacity-100",
                )}
              >
                <NodeMarkSvg type={n.type} className="size-3.5 text-muted-foreground" />
                <span className="truncate">{n.title || id}</span>
                {repeats(id) && <span className="shrink-0 text-[10px] text-muted-foreground">{n.type}</span>}
              </button>
            </li>
          );
        })}
        {fed.length > FED_MAX && (
          <li>
            <span className="inline-flex rounded-md border border-dashed px-2 py-0.5 text-xs text-muted-foreground">+ {fed.length - FED_MAX} more</span>
          </li>
        )}
      </ul>
    </Stage>
  );
}

/** Raw → Source → Concepts it feeds, for the drawn source; "no source yet" when the concept has none. Fixed height. */
export function PipelineStrip({ vault, concept, draw, onPick, onRead }: { vault: Vault; concept: string; draw: SourceDraw | null; onPick: (id: string) => void; onRead: (slug: string) => void }) {
  const source = draw ? vault.byId.get(draw.id) : undefined;
  const via = draw?.via ? vault.byId.get(draw.via) : undefined;
  const empty = (title: string, dots: ReactNode, text: string) => (
    <Stage title={title} dots={dots} className="border-dashed bg-transparent">
      <p className="m-auto text-center text-xs text-muted-foreground">{text}</p>
    </Stage>
  );
  return (
    <section aria-labelledby="home-pipeline" className="flex min-w-0 flex-col" data-tour="home-pipeline" data-testid="home-pipeline">
      <h2 id="home-pipeline" className="text-center text-[10.5px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
        Knowledge pipeline for one source the concept relies on
      </h2>
      <p className="mb-1.5 text-center text-[11px] text-muted-foreground">click any source node to see its pipeline</p>
      <div className="grid grid-cols-1 items-stretch gap-3 md:grid-cols-[1fr_40px_1fr_40px_1fr]">
        {source ? (
          <>
            <RawStage key={`raw-${source.id}`} source={source} />
            <StageArrow label="catalog" />
            <SourceStage source={source} onRead={onRead} />
            <StageArrow label="digest" />
            <ConceptsStage vault={vault} source={source.id} concept={concept} onPick={onPick} />
          </>
        ) : (
          <>
            {empty("Raw", <Dot color={RAW_COLOR} />, "No raw file yet.")}
            <StageArrow label="catalog" />
            {empty("Source", <ShapeIcon shape="source" className="size-3.5 text-muted-foreground" />, "No source yet: this concept is not backed by a source in the vault.")}
            <StageArrow label="digest" />
            {empty("Concepts it feeds", <ConceptDots />, "Nothing fed yet.")}
          </>
        )}
      </div>
      <p className="mt-1.5 h-4 truncate text-center text-xs leading-4 text-muted-foreground">{via ? `Reached through the idea ${via.title || via.id}.` : ""}</p>
    </section>
  );
}
