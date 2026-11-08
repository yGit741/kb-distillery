import { useQueryClient } from "@tanstack/react-query";
import { FolderOpen, Upload } from "lucide-react";
import { useRef, useState, type DragEvent, type FormEvent } from "react";
import { useDataSource } from "@/api";
import type { InboxFileResult } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

const STATUS_LABEL: Record<string, string> = { added: "Added", duplicate: "Already here", refused: "Refused" };

const errorLine = (e: unknown) => (e instanceof Error ? e.message : String(e));

/** Drop zone plus a "link a folder" form: both put sources in the kb inbox (no LLM). Used by the first-run card and the pipeline screen. */
export function AddSources({ className }: { className?: string }) {
  const ds = useDataSource();
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState<InboxFileResult[]>([]);
  const [error, setError] = useState<string>();
  const [folder, setFolder] = useState("");
  const [linked, setLinked] = useState<string>();
  const [folderError, setFolderError] = useState<string>();

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["graph"] });
    void qc.invalidateQueries({ queryKey: ["pipeline"] });
  };

  async function send(files: File[]) {
    if (!files.length || busy) return;
    setBusy(true);
    setError(undefined);
    try {
      const r = await ds.addInboxFiles(files);
      setResults(r.files);
      refresh();
    } catch (e) {
      setResults([]);
      setError(errorLine(e));
    } finally {
      setBusy(false);
    }
  }

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    void send(Array.from(e.dataTransfer.files));
  };

  async function link(e: FormEvent) {
    e.preventDefault();
    const path = folder.trim();
    if (!path) return;
    setFolderError(undefined);
    setLinked(undefined);
    try {
      const r = await ds.linkInboxFolder(path);
      setLinked(`${r.files_catalogued} ${r.files_catalogued === 1 ? "file" : "files"} catalogued from this folder.`);
      refresh();
    } catch (err) {
      setFolderError(errorLine(err));
    }
  }

  return (
    <div className={cn("flex flex-col gap-3", className)} data-testid="add-sources">
      <div
        role="button"
        tabIndex={0}
        aria-label="Drop files here"
        data-over={over}
        onClick={() => input.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            input.current?.click();
          }
        }}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={onDrop}
        className={cn(
          "flex cursor-pointer items-center gap-3 rounded-lg border border-dashed bg-background px-4 py-3 text-left transition-colors hover:bg-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring",
          over && "border-primary bg-accent-soft",
        )}
      >
        <span className="text-muted-foreground [&_svg]:size-5"><Upload /></span>
        <span className="flex flex-col">
          <span className="text-sm font-medium text-foreground">{busy ? "Adding…" : "Drop files here"}</span>
          <span className="text-xs text-muted-foreground">Or click to pick files. Papers, notes and articles go to the inbox.</span>
        </span>
        <input
          ref={input}
          type="file"
          multiple
          hidden
          data-testid="add-sources-input"
          onChange={(e) => {
            void send(Array.from(e.target.files ?? []));
            e.target.value = "";
          }}
        />
      </div>
      {error && <p role="alert" className="text-sm text-bad">{error}</p>}
      {results.length > 0 && (
        <ul aria-label="Add results" className="flex flex-col gap-1 text-sm">
          {results.map((r, i) => (
            <li key={`${r.name}-${i}`} className="flex flex-wrap gap-x-2">
              <span className="min-w-0 break-all text-foreground">{r.name}</span>
              <span className={cn("text-xs", r.status === "refused" ? "text-bad" : "text-muted-foreground")}>
                {STATUS_LABEL[r.status] ?? r.status}{r.reason ? `: ${r.reason}` : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={(e) => void link(e)} className="flex flex-col gap-2" aria-label="Link a local folder">
        <label htmlFor="add-sources-folder" className="flex items-center gap-2 text-sm font-medium text-foreground">
          <span className="text-muted-foreground [&_svg]:size-4"><FolderOpen /></span>
          Link a local folder
        </label>
        <div className="flex gap-2">
          <Input id="add-sources-folder" value={folder} onChange={(e) => setFolder(e.target.value)} placeholder="Paste a folder path, e.g. /Users/me/papers" />
          <Button type="submit" size="sm" variant="secondary" disabled={!folder.trim()}>Link</Button>
        </div>
        {linked && <p className="text-sm text-muted-foreground">{linked}</p>}
        {folderError && <p role="alert" className="text-sm text-bad">{folderError}</p>}
      </form>
    </div>
  );
}
