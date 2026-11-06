import { useEffect, useRef, useState } from "react";
import { LINE_COPY } from "../shell/copy";
import { isParseError, parse } from "./grammar";
import type { Layer } from "./model";

const ROW = "flex min-h-6 items-center gap-2 px-1 text-xs text-muted-foreground";

/**
 * The quiet row under the search line while a `>` sentence is previewed (flag graph-intent): the resolved lines
 * joined by " · " and the node count. Clicking it, or Tab from the input, turns it into a field holding one line per
 * layer; Enter reads each line with the grammar and applies exactly what is written. A line that cannot be read
 * shows its reason under the field and nothing applies. The row keeps its height whether or not there is a preview,
 * so the panel below does not move.
 */
export function ResolvedLine({
  lines,
  count,
  editing,
  onEditing,
  onApply,
}: {
  lines: string[] | null;
  count: number;
  editing: boolean;
  onEditing: (on: boolean) => void;
  onApply: (layers: Layer[]) => void;
}) {
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const field = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    if (!editing) return;
    setDraft((lines ?? []).join("\n"));
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
    setError(null);
    onApply(layers);
  };

  if (!lines) return <div className={ROW} data-testid="resolved-line" aria-hidden />;
  if (!editing)
    return (
      <button type="button" className={`${ROW} w-full text-left hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring`} data-testid="resolved-line" title={LINE_COPY.preview.edit} onClick={() => onEditing(true)}>
        <span className="min-w-0 flex-1 truncate text-foreground">{lines.join(" · ")}</span>
        <span className="shrink-0">{LINE_COPY.preview.count(count)}</span>
      </button>
    );
  return (
    <div className="px-1 py-1 text-xs" data-testid="resolved-line">
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
