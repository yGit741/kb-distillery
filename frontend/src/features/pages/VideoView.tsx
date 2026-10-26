import { ExternalLink } from "lucide-react";
import type { VideoBundle, VideoFrame, VideoSection } from "@/api/types";
import { useDataSource } from "@/api";
import { Markdown } from "@/components/Markdown";
import { ErrorState, Loading } from "@/components/states";
import { cn } from "@/lib/utils";
import { useApiQuery } from "@/lib/useApiQuery";
import { Fold } from "./parts";

/** A Source page whose raw item is a scrap-youtube bundle (`raw/videos/<dir>/video.md`). */
export const isVideoRaw = (raw: string) => /^raw\/videos\/[^/]+\/video\.md$/.test(raw);

const clock = (s: number) => {
  const t = Math.floor(s);
  return `${Math.floor(t / 3600)}:${String(Math.floor((t % 3600) / 60)).padStart(2, "0")}:${String(t % 60).padStart(2, "0")}`;
};
const at = (url: string, s: number) => `${url}&t=${Math.floor(s)}s`;
const stampSeconds = (stamp: string) => stamp.split(":").reduce((a, x) => a * 60 + Number(x), 0);

/** `$$x$$` on one line is inline math to remark-math; give each one its own display block. */
export const displayMath = (t: string) => t.replace(/^\s*\$\$(.+?)\$\$\s*$/gm, (_m, x: string) => `\n$$\n${x}\n$$\n`);

/**
 * The video under its page: chapters, description and comments, then the transcript by chapter with each kept
 * frame beside what was read from it. Local only — a share build has no raw files, so it shows nothing.
 */
export function VideoView({ raw, className }: { raw: string; className?: string }) {
  const ds = useDataSource();
  const q = useApiQuery(["video", raw], (d) => d.getVideo(raw), { enabled: ds.kind === "http", retry: false });
  if (ds.kind !== "http") return null;
  return (
    <section aria-label="Video" className={cn("flex min-w-0 flex-col gap-4 border-t pt-4", className)}>
      {q.isError ? (
        <ErrorState title="The video bundle could not be read" error={q.error} onRetry={() => q.refetch()} />
      ) : !q.data ? (
        <Loading label="Loading the video" rows={3} />
      ) : (
        <Bundle v={q.data} frameUrl={(f) => ds.rawFileUrl(f.path)} />
      )}
    </section>
  );
}

function Bundle({ v, frameUrl }: { v: VideoBundle; frameUrl: (f: VideoFrame) => string | null }) {
  const byChapter: { chapter: string; sections: VideoSection[] }[] = [];
  for (const s of v.sections ?? []) {
    const last = byChapter[byChapter.length - 1];
    if (last && last.chapter === s.chapter) last.sections.push(s);
    else byChapter.push({ chapter: s.chapter, sections: [s] });
  }
  const frames = v.frames ?? [];
  const chapters = v.chapters ?? [];
  const links = v.links ?? [];
  const comments = v.comments ?? [];
  // each frame in the last section starting at or before it (one shown before the first caption goes first)
  const sections = v.sections ?? [];
  const home = (t: number) => sections.reduce((at, s, i) => (s.start <= t ? i : at), 0);
  const inSection = (s: VideoSection) => frames.filter((f) => sections[home(f.t)] === s);
  return (
    <>
      <header className="flex flex-col gap-2">
        <h2 className="text-lg font-semibold">Video</h2>
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
          <span className="tabular-nums">{clock(v.duration)}</span>
          {v.channel && <span>{v.channel}</span>}
          <span>{chapters.length} chapters</span>
          <span>{frames.length} frames</span>
          <span>transcript {v.subs_kind ?? "none"}</span>
          <span>tier {v.tier}</span>
          <a className="inline-flex items-center gap-1 text-primary hover:underline" href={v.url} target="_blank" rel="noopener noreferrer">
            YouTube <ExternalLink className="size-3" aria-hidden />
          </a>
        </p>
        {chapters.length > 0 && (
          <nav aria-label="Chapters" className="flex flex-wrap gap-1.5">
            {chapters.map((c) => (
              <a key={c.start} href={at(v.url, c.start)} target="_blank" rel="noopener noreferrer"
                className="rounded-md border px-2 py-1 text-xs hover:bg-accent">
                <span className="tabular-nums text-muted-foreground">{clock(c.start)}</span> {c.title}
              </a>
            ))}
          </nav>
        )}
      </header>

      <div className="grid gap-3 md:grid-cols-2">
        <Fold title="Description" count={links.length}>
          <p className="whitespace-pre-wrap">{v.description || "No description."}</p>
          {links.length > 0 && (
            <ul className="mt-2 flex flex-col gap-1">
              {links.map((l) => (
                <li key={l} className="truncate">
                  <a href={l} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">{l}</a>
                </li>
              ))}
            </ul>
          )}
        </Fold>
        <Fold title="Top comments" count={comments.length}>
          {comments.length === 0 ? (
            <p className="text-muted-foreground">No comment with a timestamp, a link or a question.</p>
          ) : (
            <ul className="flex max-h-96 flex-col gap-3 overflow-auto">
              {comments.map((c, i) => (
                <li key={i} className="border-b pb-2 last:border-b-0">
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span>{c.author}</span>
                    <span className="tabular-nums">{c.likes} likes</span>
                  </div>
                  <p className="mt-1 whitespace-pre-wrap">{c.text}</p>
                  {(c.stamps ?? []).length > 0 && (
                    <div className="mt-1 flex flex-wrap gap-2">
                      {(c.stamps ?? []).map((s) => (
                        <a key={s} href={at(v.url, stampSeconds(s))} target="_blank" rel="noopener noreferrer"
                          className="text-xs text-primary hover:underline">{s}</a>
                      ))}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Fold>
      </div>

      {byChapter.length === 0 && <p className="text-sm text-muted-foreground">No English transcript was downloaded for this video.</p>}
      {byChapter.map(({ chapter, sections }) => (
        <div key={`${chapter}-${sections[0]?.start}`} className="flex flex-col gap-4">
          {chapter && <h3 className="text-base font-semibold">{chapter}</h3>}
          {sections.map((s) => (
            <div key={s.start} className="flex flex-col gap-3 border-b pb-4 last:border-b-0">
              <div className="max-w-3xl">
                <a href={at(v.url, s.start)} target="_blank" rel="noopener noreferrer"
                  className="text-sm font-medium tabular-nums text-primary hover:underline">
                  {clock(s.start)} – {clock(s.end)}
                </a>
                <p className="mt-1 text-sm leading-relaxed">{s.text}</p>
              </div>
              {inSection(s).map((f) => <FrameCard key={f.file} f={f} url={frameUrl(f)} />)}
            </div>
          ))}
        </div>
      ))}
    </>
  );
}

/** One frame: the image (sticky beside a long read) and what was read from it, wide enough for display math. */
function FrameCard({ f, url }: { f: VideoFrame; url: string | null }) {
  const read = f.read?.text ?? "";
  const ocr = f.ocr ?? [];
  return (
    <figure className="grid gap-4 rounded-lg border bg-card p-3 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
      <div className="flex flex-col gap-1 self-start lg:sticky lg:top-16">
        {url && (
          <a href={url} target="_blank" rel="noopener noreferrer">
            <img src={url} alt={`Frame at ${clock(f.t)}`} loading="lazy" className="w-full rounded" />
          </a>
        )}
        <figcaption className="flex justify-between text-xs tabular-nums text-muted-foreground">
          <span>{clock(f.t)}</span>
          <span>{f.kind}</span>
        </figcaption>
      </div>
      <div className="flex min-w-0 flex-col gap-2">
        {read ? (
          <Markdown className="text-sm [&_.katex-display]:my-1 [&_.katex-display]:overflow-x-auto [&_.katex-display]:overflow-y-hidden">
            {displayMath(read)}
          </Markdown>
        ) : ocr.length > 0 ? (
          <div className="flex flex-col gap-1">
            <span className="text-xs text-muted-foreground">Local OCR{f.conf != null ? ` · confidence ${f.conf}` : ""}</span>
            <pre className="whitespace-pre-wrap font-mono text-xs">{ocr.join("\n")}</pre>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">No text on this frame.</p>
        )}
        {read && ocr.length > 0 && (
          <details className="text-xs">
            <summary className="cursor-pointer text-muted-foreground">Local OCR ({ocr.length} lines)</summary>
            <pre className="mt-1 whitespace-pre-wrap font-mono">{ocr.join("\n")}</pre>
          </details>
        )}
      </div>
    </figure>
  );
}
