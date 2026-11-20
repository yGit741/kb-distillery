import { FilePlus2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useDataSource } from "@/api";
import { Button } from "@/components/ui/button";
import { ACCEPT, fileProblem, urlProblem } from "@/features/ingest/model";
import { cn } from "@/lib/utils";

/**
 * Add knowledge without leaving the deck: drop a file anywhere on the screen, choose one, or paste a link. The source
 * is filed under raw/ and read in full; the queue shows it reading, and its pages come back as cards (a cover first).
 */
export function SourceDrop({ disabled, sample, onStarted, dropped }: { disabled: boolean; sample: boolean; onStarted: (jobId: string) => void; dropped: File | null }) {
  const ds = useDataSource();
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const picker = useRef<HTMLInputElement>(null);

  const start = async (input: { file?: File; url?: string }) => {
    setError(null);
    const problem = input.file ? fileProblem(input.file) : urlProblem(input.url ?? "");
    if (problem) return setError(problem);
    if (sample) return setError("This is the sample deck: in your KB the source would be read now and its pages would arrive here as cards.");
    try {
      const started = await ds.startIngest({ ...input, tier: "full" });
      onStarted(started.job_id);
      setUrl("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start reading it.");
    }
  };
  const startRef = useRef(start);
  startRef.current = start;
  useEffect(() => {
    if (dropped) void startRef.current({ file: dropped });
  }, [dropped]);

  return (
    <section className="flex flex-col gap-1.5" data-tour="review-drop" aria-label="Add a source">
      <form
        className={cn("flex min-h-14 flex-col justify-center gap-1 rounded-lg border border-dashed px-3 py-2 text-sm", disabled && "opacity-60")}
        onSubmit={(e) => {
          e.preventDefault();
          if (url.trim()) void start({ url: url.trim() });
        }}
      >
        <div className="flex items-center gap-2">
          <FilePlus2 className="size-4 shrink-0 text-muted-foreground" aria-hidden />
          <input
            value={url}
            disabled={disabled}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => e.stopPropagation()}
            aria-label="Paste a link to add it"
            placeholder="Drop a file or paste a link"
            className="min-w-0 flex-1 bg-transparent outline-none placeholder:text-muted-foreground"
          />
        </div>
        <div className="flex items-center gap-1">
          <input ref={picker} type="file" accept={ACCEPT.join(",")} className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) void start({ file: f }); e.target.value = ""; }} />
          <Button type="button" size="sm" variant="ghost" className="h-6 px-2 text-xs" disabled={disabled} onClick={() => picker.current?.click()}>Choose file</Button>
          {url.trim() && <Button type="submit" size="sm" variant="secondary" className="h-6 px-2 text-xs" disabled={disabled}>Read it</Button>}
        </div>
      </form>
      {error && <p role="alert" className="text-xs text-bad">{error}</p>}
    </section>
  );
}
