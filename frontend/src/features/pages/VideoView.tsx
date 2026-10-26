import { ExternalLink } from "lucide-react";
import type { VideoAnchor, VideoBundle, VideoSection } from "@/api/types";
import { useDataSource } from "@/api";
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

/**
 * The raw video under its page: chapters, description and comments, then the transcript by chapter with the
 * section's anchors (candidate frames, scored) as thumbnails. The frames a digest read live in the page body
 * (## Frames). Local only — a share build has no raw files, so it shows nothing.
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
        <Bundle v={q.data} thumbUrl={(a) => ds.rawFileUrl(a.path)} />
      )}
    </section>
  );
}

function Bundle({ v, thumbUrl }: { v: VideoBundle; thumbUrl: (a: VideoAnchor) => string | null }) {
  const sections = v.sections ?? [];
  const anchors = v.anchors ?? [];
  const chapters = v.chapters ?? [];
  const links = v.links ?? [];
  const comments = v.comments ?? [];
  const byChapter: { chapter: string; sections: VideoSection[] }[] = [];
  for (const s of sections) {
    const last = byChapter[byChapter.length - 1];
    if (last && last.chapter === s.chapter) last.sections.push(s);
    else byChapter.push({ chapter: s.chapter, sections: [s] });
  }
  // each anchor in the last section starting at or before it (one before the first caption goes first)
  const home = (t: number) => sections.reduce((i, s, k) => (s.start <= t ? k : i), 0);
  const inSection = (s: VideoSection) => anchors.filter((a) => sections[home(a.t)] === s);
  return (
    <>
      <header className="flex flex-col gap-2">
        <h2 className="text-lg font-semibold">Video</h2>
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
          <span className="tabular-nums">{clock(v.duration)}</span>
          {v.channel && <span>{v.channel}</span>}
          <span>{chapters.length} chapters</span>
          <span>{anchors.length} anchors</span>
          <span>transcript {v.subs_kind ?? "none"}</span>
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

      {anchors.length === 0 && (
        <p className="text-sm text-muted-foreground">No anchors in this bundle — re-scrap the video to find them.</p>
      )}
      {byChapter.length === 0 && <p className="text-sm text-muted-foreground">No English transcript was downloaded for this video.</p>}
      {byChapter.map(({ chapter, sections: secs }) => (
        <div key={`${chapter}-${secs[0]?.start}`} className="flex flex-col gap-4">
          {chapter && <h3 className="text-base font-semibold">{chapter}</h3>}
          {secs.map((s) => (
            <div key={s.start} className="flex flex-col gap-2 border-b pb-4 last:border-b-0">
              <div className="max-w-3xl">
                <a href={at(v.url, s.start)} target="_blank" rel="noopener noreferrer"
                  className="text-sm font-medium tabular-nums text-primary hover:underline">
                  {clock(s.start)} – {clock(s.end)}
                </a>
                <p className="mt-1 text-sm leading-relaxed">{s.text}</p>
              </div>
              {inSection(s).length > 0 && (
                <ul aria-label={`Anchors ${clock(s.start)}`} className="flex gap-2 overflow-x-auto pb-1">
                  {inSection(s).map((a) => <AnchorThumb key={a.t} a={a} url={thumbUrl(a)} videoUrl={v.url} />)}
                </ul>
              )}
            </div>
          ))}
        </div>
      ))}
    </>
  );
}

/** One anchor: its thumbnail (opens full size), the time (opens the video there) and its score and reasons. */
function AnchorThumb({ a, url, videoUrl }: { a: VideoAnchor; url: string | null; videoUrl: string }) {
  const why = (a.why ?? []).join(" · ");
  return (
    <li className={cn("w-40 shrink-0 rounded-md border bg-card p-1 text-xs", a.score < 1 && "opacity-60")}
      title={`score ${a.score}${why ? ` · ${why}` : ""}`}>
      {url && (
        <a href={url} target="_blank" rel="noopener noreferrer">
          <img src={url} alt={`Anchor at ${clock(a.t)}`} loading="lazy" className="w-full rounded" />
        </a>
      )}
      <div className="mt-1 flex justify-between tabular-nums text-muted-foreground">
        <a href={at(videoUrl, a.t)} target="_blank" rel="noopener noreferrer" className="hover:underline">{clock(a.t)}</a>
        <span>score {a.score}</span>
      </div>
      {why && <p className="truncate text-muted-foreground">{why}</p>}
    </li>
  );
}
