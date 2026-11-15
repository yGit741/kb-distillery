import { useEffect, useRef, useState } from "react";
import { LINE_COPY } from "../shell/copy";
import { isParseError, parse } from "./grammar";
import type { Layer } from "./model";

const ROW = "flex min-h-6 items-center gap-2 px-1 text-sm text-muted-foreground";
/** The "Read as" row: as tall before the first Enter as with one line read (a code line and the count under it), so
 * the first Enter does not move the panel. */
const READ = "flex min-h-12 items-start gap-2 px-1 py-1 text-sm text-muted-foreground";
/** Lines shown; the rest are counted ("+2 more") and all of them are in the edit field. */
const READ_MAX = 3;

/**
 * The quiet row under the search line while a `>` sentence is previewed (flag graph-intent): the resolved lines
 * joined by " · " and the node count. Clicking it, or Tab from the input, turns it into a field holding one line per
 * layer; Enter reads each line with the grammar and applies exactly what is written. A line that cannot be read
 * shows its reason under the field and nothing applies. The row keeps its height whether or not there is a preview,
 * so the panel below does not move.
 *
 * With flag graph-algos it is the "Read as" row: the query the line became, one code line per layer with page titles
 * for slugs (`display`), labelled by who read it (the rules or the model), and the count with the keys under it.
 * Before the first Enter it says where the query will show. Written lines go through `resolve` (names to pages)
 * before they apply.
 */
export function ResolvedLine({
  lines,
  count,
  offScreen = 0,
  editing,
  onEditing,
  onApply,
  readAs = false,
  by = "rules",
  note = "",
  display = (l) => l,
  resolve,
}: {
  lines: string[] | null;
  count: number;
  /** How many of the `count` pages are not drawn in the current view (applying draws them). */
  offScreen?: number;
  editing: boolean;
  onEditing: (on: boolean) => void;
  onApply: (layers: Layer[]) => void;
  /** Flag graph-algos: the "Read as" row. */
  readAs?: boolean;
  /** Who read the line into these layers. */
  by?: "rules" | "model";
  /** The model's account of its reading (what it left out), shown under the lines when the model read them. */
  note?: string;
  /** A resolved line as it is shown and edited (page titles for slugs). */
  display?: (line: string) => string;
  /** Written layers with their names looked up, or why they cannot apply. */
  resolve?: (layers: Layer[]) => Layer[] | string;
}) {
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const field = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    if (!editing) return;
    setDraft((lines ?? []).map(display).join("\n"));
    setError(null);
    field.current?.focus();
    // the draft starts from the lines as they were when editing began
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editing]);

  const submit = () => {
    const rows = draft.split("\n").map((l) => l.trim()).filter(Boolean);
    if (!rows.length) return setError(LINE_COPY.preview.parseError(1, "write a line starting with show, hide or style"));
    const layers: Layer[] = [];
    for (const [i, row] of rows.entries()) {
      const l = parse(row);
      if (isParseError(l)) return setError(LINE_COPY.preview.parseError(i + 1, l.error));
      layers.push({ ...l, text: row });
    }
    const ready = resolve ? resolve(layers) : layers;
    if (typeof ready === "string") return setError(ready);
    setError(null);
    onApply(ready);
  };

  if (readAs && !editing) {
    const P = LINE_COPY.preview;
    if (!lines)
      return (
        <div className={READ} data-testid="resolved-line">
          <span className="text-xs">{P.readAsWaiting}</span>
        </div>
      );
    const shown = lines.slice(0, READ_MAX).map(display);
    return (
      <button type="button" className={`${READ} w-full text-left hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring`} data-testid="resolved-line" title={P.edit} onClick={() => onEditing(true)}>
        <span className="mt-0.5 shrink-0 whitespace-nowrap text-xs font-medium" data-testid="read-as-by">
          {by === "model" ? P.readByModel : P.readAs}
        </span>
        <span className="min-w-0 flex-1">
          {shown.map((l, i) => (
            <code key={i} className="mb-0.5 block break-words rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-foreground" data-testid="read-as-line">
              {l}
            </code>
          ))}
          {by === "model" && note && (
            <span className="block text-xs" data-testid="read-as-note">
              {note}
            </span>
          )}
          <span className="block text-xs">
            {lines.length > READ_MAX && `${P.more(lines.length - READ_MAX)} · `}
            {P.count(count)}
            {offScreen > 0 && `, ${P.offScreen(offScreen, count)}`}
            {` · ${P.hint}`}
          </span>
        </span>
      </button>
    );
  }
  if (!lines) return <div className={ROW} data-testid="resolved-line" aria-hidden />;
  if (!editing)
    return (
      <button type="button" className={`${ROW} w-full text-left hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring`} data-testid="resolved-line" title={LINE_COPY.preview.edit} onClick={() => onEditing(true)}>
        <span className="min-w-0 flex-1 truncate text-foreground">{lines.join(" · ")}</span>
        <span className="shrink-0">
          {LINE_COPY.preview.count(count)}
          {offScreen > 0 && `, ${LINE_COPY.preview.offScreen(offScreen, count)}`}
        </span>
        <span className="shrink-0 text-xs">{LINE_COPY.preview.hint}</span>
      </button>
    );
  return (
    <div className="px-1 py-1 text-sm" data-testid="resolved-line">
      <textarea
        ref={field}
        aria-label={LINE_COPY.preview.editLabel}
        className="block w-full resize-none rounded border bg-transparent px-2 py-1 font-mono text-foreground"
        rows={Math.max(1, draft.split("\n").length)}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          e.stopPropagation();
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit();
          } else if (e.key === "Escape") {
            e.preventDefault();
            onEditing(false);
          }
        }}
      />
      <p className={error ? "mt-1 text-destructive" : "mt-1 text-muted-foreground"} role={error ? "alert" : undefined}>
        {error ?? LINE_COPY.preview.editHint}
      </p>
    </div>
  );
}
