import { Ellipsis, GitMerge, Scissors, Split } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { useVariant, VARIANTS } from "@/components/variants";
import { useFlag } from "@/flags/useFlag";
import { KINDS, parseSlash, slashMatches, type RestructureKind } from "./lib";
import { useRestructureStore } from "./store";

const LABEL: Record<RestructureKind, string> = { merge: "Merge into…", split: "Split…", extract: "Extract…" };
const HINT: Record<RestructureKind, string> = {
  merge: "/merge @page — combine pages into one",
  split: "/split — cut this page into pages",
  extract: "/extract — move a block range to a new page",
};
const ICON = { merge: GitMerge, split: Split, extract: Scissors } as const;

/** The restructure entry variant in force. `command` needs the page chat; without it the menu is the entry. */
export function useRestructureEntry(chatAvailable: boolean): "menu" | "command" {
  const spec = VARIANTS["restructure-entry"]!;
  const [v] = useVariant("restructure-entry", spec.options.map((o) => o.id), spec.default);
  return v === "command" && chatAvailable ? "command" : "menu";
}

/** Page header piece of the `menu` variant: a quiet Restructure button with the three actions. */
export function RestructureMenu({ chatAvailable }: { chatAvailable: boolean }) {
  const entry = useRestructureEntry(chatAvailable);
  const show = useRestructureStore((s) => s.show);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);
  if (entry === "command")
    return (
      <span className="text-xs text-muted-foreground" title="Type these in the page chat" data-tour="page-restructure">
        <kbd className="rounded border px-1 font-mono text-[0.7rem]">/merge</kbd> <kbd className="rounded border px-1 font-mono text-[0.7rem]">/split</kbd>{" "}
        <kbd className="rounded border px-1 font-mono text-[0.7rem]">/extract</kbd>
      </span>
    );
  return (
    <div ref={ref} className="relative" data-tour="page-restructure">
      <Button variant="ghost" size="sm" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <Ellipsis /> Restructure
      </Button>
      {open && (
        <ul role="menu" aria-label="Restructure" className="absolute left-0 top-full z-30 mt-1 w-44 rounded-md border bg-card p-1 shadow-md">
          {KINDS.map((k) => {
            const Icon = ICON[k];
            return (
              <li key={k} role="none">
                <button
                  type="button"
                  role="menuitem"
                  className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-muted"
                  onClick={() => (setOpen(false), show(k))}
                >
                  <Icon className="size-4 text-muted-foreground" aria-hidden /> {LABEL[k]}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

/**
 * For the page chat composer (`command` variant): `run(message, mentions)` opens the dialog for "/merge @page" and
 * friends and returns true when it handled the message; `enabled` says whether hints and commands are live.
 */
export function useRestructureSlash() {
  const on = useFlag("ui.restructure");
  const entry = useRestructureEntry(true);
  const show = useRestructureStore((s) => s.show);
  const enabled = on && entry === "command";
  return {
    enabled,
    run: (message: string, mentions: readonly string[]): boolean => {
      const cmd = enabled ? parseSlash(message, mentions) : null;
      if (!cmd) return false;
      show(cmd.kind, cmd.mentions);
      return true;
    },
  };
}

/** The command list above the composer while the draft is "/", "/me" … */
export function SlashHints({ draft, onPick }: { draft: string; onPick: (kind: RestructureKind) => void }) {
  const hits = slashMatches(draft);
  if (!hits.length) return null;
  return (
    <ul role="listbox" aria-label="Restructure commands" className="absolute bottom-full left-4 right-4 mb-1 rounded-md border bg-card p-1 shadow-md">
      {hits.map((k) => (
        <li key={k} role="option" aria-selected={false} onMouseDown={(e) => (e.preventDefault(), onPick(k))} className="cursor-pointer rounded px-2 py-1 text-sm hover:bg-muted">
          {HINT[k]}
        </li>
      ))}
    </ul>
  );
}
