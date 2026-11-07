/**
 * Quick capture: one small dialog, reachable from any screen (⌘⇧Space, or ⌘K → "Quick thought").
 * Appends to think/inbox.md under today's date and gets out of the way.
 */
import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Feather } from "lucide-react";
import { useDataSource } from "@/api";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { captureFooter, useUi } from "@/app/ui-store";

export default function QuickCapture() {
  const { captureOpen, setCaptureOpen, captureContext } = useUi();
  const footer = captureFooter(captureContext);
  const ds = useDataSource();
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const [saved, setSaved] = useState(false);
  const area = useRef<HTMLTextAreaElement>(null);
  const closeTimer = useRef<number | undefined>(undefined);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.code === "Space") {
        e.preventDefault();
        setCaptureOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setCaptureOpen]);

  const save = useMutation({
    mutationFn: (t: string) => ds.captureThink(t),
    onSuccess: () => {
      setSaved(true);
      setText("");
      void qc.invalidateQueries({ queryKey: ["think"] }); // list + a cached/open inbox.md
      window.clearTimeout(closeTimer.current);
      closeTimer.current = window.setTimeout(() => {
        setSaved(false);
        setCaptureOpen(false);
      }, 900);
    },
  });

  const submit = () => {
    if (text.trim() && !save.isPending) save.mutate(footer ? `${text.trimEnd()}\n${footer}` : text);
  };

  return (
    <Dialog
      open={captureOpen}
      onOpenChange={(open) => {
        setCaptureOpen(open);
        window.clearTimeout(closeTimer.current);
        if (!open) {
          setSaved(false);
          save.reset();
        }
      }}
    >
      <DialogContent className="max-w-md gap-2 p-4">
        <DialogTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
          <Feather className="size-4" aria-hidden /> Quick thought
        </DialogTitle>
        <DialogDescription className="sr-only">Append a thought to think/inbox.md</DialogDescription>
        {saved ? (
          <p className="py-6 text-center text-sm text-muted-foreground" role="status">
            Saved to think/inbox.md ✓
          </p>
        ) : (
          <>
            <textarea
              ref={area}
              autoFocus
              rows={3}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  submit();
                }
              }}
              placeholder="A quick thought…"
              aria-label="Quick thought"
              className="w-full resize-none rounded-md border bg-background p-2 text-sm outline-none focus:ring-1 focus:ring-ring"
            />
            {footer && (
              <p className="whitespace-pre-wrap break-words text-xs text-muted-foreground" aria-label="Attached context">
                {footer}
              </p>
            )}
            {save.isError && <p className="text-xs text-bad">Could not save — {String((save.error as Error).message ?? save.error)}</p>}
            <p className="text-xs text-muted-foreground">⏎ save to think/inbox.md · ⇧⏎ new line · esc close</p>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
