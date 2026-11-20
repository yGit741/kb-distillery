import { CornerDownLeft, FileText, Loader2, Quote, X } from "lucide-react";
import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { COMMANDS, matchCommands, parseCommand, type Command } from "./model";
import type { Picked } from "./ReachGraph";

export interface EditLineHandle {
  focus: (prefill?: string) => void;
  clear: () => void;
}

type Page = { slug: string; title: string };

const NONE: Picked[] = [];
const COMMAND_HINT: Record<string, string> = { "/merge": "Fold another page in", "/split": "Cut this page in two" };
const quote = (m: string) => `"${m.length > 28 ? `${m.slice(0, 28)}…` : m}"`;

/**
 * The one line under a card: say what should change (the model rewrites the card), or a command (`/merge @page`,
 * `/split`), always shown under it. What is selected (pages in the graph, passages marked on the card) shows as
 * chips above it and goes with the next sentence. Enter sends, Esc cancels, ↑ in an empty line brings back the last
 * sentence.
 */
export const EditLine = forwardRef<EditLineHandle, {
  busy: string | null;
  error: string | null;
  disabled?: boolean;
  disabledReason?: string;
  slug: string;
  findPages: (q: string) => Promise<Page[]>;
  onSubmit: (cmd: Command) => void;
  onCancel: () => void;
  /** pages picked in the graph and passages marked on the card: they go with the next sentence */
  context?: { pages: Picked[]; marks: string[] };
  onRemovePage?: (slug: string) => void;
  onRemoveMark?: (i: number) => void;
  onClearContext?: () => void;
  /** the pages /merge offers before anything is typed: the selection first, then the card's neighbours */
  suggested?: Picked[];
}>(function EditLine({ busy, error, disabled, disabledReason, slug, findPages, onSubmit, onCancel, context, onRemovePage, onRemoveMark, onClearContext, suggested = NONE }, ref) {
  const [value, setValue] = useState("");
  const [last, setLast] = useState("");
  const [pages, setPages] = useState<Page[]>([]);
  const [pick, setPick] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  useImperativeHandle(ref, () => ({
    focus: (prefill) => {
      if (prefill !== undefined) setValue(prefill);
      requestAnimationFrame(() => input.current?.focus());
    },
    clear: () => setValue(""),
  }));

  const merging = /^\/merge(\s|$)/.test(value);
  const splitting = /^\/split\s/.test(value);
  const query = merging ? value.replace(/^\/merge\s*@?/, "") : "";
  const selectedPages = context?.pages ?? NONE;
  useEffect(() => {
    if (!merging) return setPages([]);
    if (!query) {
      const offer = selectedPages.length > 1 ? selectedPages : [...selectedPages, ...suggested.filter((p) => !selectedPages.some((q) => q.slug === p.slug))];
      return setPages(offer.filter((p) => p.slug !== slug).slice(0, 6));
    }
    let live = true;
    const t = setTimeout(() => {
      findPages(query).then((rows) => live && setPages(rows.filter((p) => p.slug !== slug).slice(0, 6)), () => live && setPages([]));
    }, 150);
    return () => {
      live = false;
      clearTimeout(t);
    };
  }, [merging, query, slug, findPages, selectedPages, suggested]);
  useEffect(() => setPick(0), [pages]);

  const menu = matchCommands(value);
  const send = (cmd: Command | null) => {
    if (!cmd) return;
    if (cmd.kind === "instruction") setLast(cmd.text);
    onSubmit(cmd);
    if (cmd.kind === "merge" || cmd.kind === "split") setValue("");
  };
  const help = parseCommand(value)?.kind === "help";
  const chips = (context?.pages.length ?? 0) + (context?.marks.length ?? 0);
  const start = (name: string) => {
    if (name === "/merge") setValue(selectedPages.length === 1 ? `/merge @${selectedPages[0]!.slug}` : "/merge @");
    else setValue(`${name} `);
    requestAnimationFrame(() => input.current?.focus());
  };
  const placeholder = busy ?? (disabled ? disabledReason : splitting ? "How? Leave empty to let the model decide." : chips ? "What should change in these?" : "What should change?");

  return (
    <div className="flex flex-col gap-1.5" data-tour="review-edit">
      {chips > 0 && (
        <ul className="flex flex-wrap items-center gap-1" aria-label="Goes with your next edit">
          {context!.pages.map((p) => (
            <li key={p.slug} className="flex items-center gap-1 rounded-full bg-blue-500/10 py-0.5 pl-2 pr-1 text-[11px] text-blue-800 dark:text-blue-200">
              <FileText className="size-3" aria-hidden />@{p.title}
              <button type="button" aria-label={`Remove ${p.title}`} className="rounded-full p-0.5 hover:bg-blue-500/20" onClick={() => onRemovePage?.(p.slug)}><X className="size-3" aria-hidden /></button>
            </li>
          ))}
          {context!.marks.map((m, i) => (
            <li key={`${i}-${m}`} className="flex items-center gap-1 rounded-full bg-amber-500/15 py-0.5 pl-2 pr-1 text-[11px] text-amber-900 dark:text-amber-200" title={m}>
              <Quote className="size-3" aria-hidden />{quote(m)}
              <button type="button" aria-label="Remove this passage" className="rounded-full p-0.5 hover:bg-amber-500/25" onClick={() => onRemoveMark?.(i)}><X className="size-3" aria-hidden /></button>
            </li>
          ))}
          {chips >= 3 && <li><button type="button" className="text-[11px] text-muted-foreground underline-offset-2 hover:underline" onClick={onClearContext}>Clear all</button></li>}
        </ul>
      )}
      <div className={cn("relative flex items-center gap-2 rounded-lg border bg-background px-3 py-2 focus-within:ring-2 focus-within:ring-ring", disabled && "opacity-60")}>
        {busy ? <Loader2 className="size-4 shrink-0 animate-spin text-muted-foreground" aria-hidden /> : <span className="text-xs font-medium text-muted-foreground" aria-hidden>E</span>}
        <input
          ref={input}
          value={value}
          disabled={disabled || !!busy}
          aria-label="What should change? Type / for commands"
          placeholder={placeholder}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            e.stopPropagation();
            if (e.key === "Escape") {
              if (busy) onCancel();
              setValue("");
              input.current?.blur();
            } else if (e.key === "ArrowUp" && !value && last) {
              e.preventDefault();
              setValue(last);
            } else if (merging && pages.length && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
              e.preventDefault();
              setPick((i) => (i + (e.key === "ArrowDown" ? 1 : pages.length - 1)) % pages.length);
            } else if (e.key === "Tab" && menu.length) {
              e.preventDefault();
              setValue(`${menu[0]!.name} `);
            } else if (e.key === "Enter") {
              e.preventDefault();
              if (merging && pages[pick]) send({ kind: "merge", target: pages[pick]!.slug });
              else if (menu.length === 1 && value.trim() === menu[0]!.name && menu[0]!.name === "/merge") setValue("/merge @");
              else send(parseCommand(value));
            }
          }}
          className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
        />
        {!busy && value && <CornerDownLeft className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />}
        {busy && <span className="shrink-0 text-xs text-muted-foreground">Esc to cancel</span>}

        {(menu.length > 0 || help) && (
          <ul role="listbox" aria-label="Commands" className="absolute bottom-full left-0 z-20 mb-1 w-full rounded-lg border bg-popover p-1 text-sm shadow-[var(--shadow)]">
            {(help ? COMMANDS : menu).map((c) => (
              <li key={c.name} role="option" aria-selected={false}>
                <button type="button" className="flex w-full items-baseline gap-2 rounded px-2 py-1 text-left hover:bg-accent" onMouseDown={(e) => e.preventDefault()} onClick={() => start(c.name)}>
                  <span className="font-mono">{c.name}</span>
                  <span className="text-xs text-muted-foreground">{c.args}</span>
                  <span className="ml-auto text-xs text-muted-foreground">{c.hint}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {merging && pages.length > 0 && (
          <ul role="listbox" aria-label="Merge which page into this one?" className="absolute bottom-full left-0 z-20 mb-1 w-full rounded-lg border bg-popover p-1 text-sm shadow-[var(--shadow)]">
            <li className="px-2 py-1 text-xs text-muted-foreground">{query ? "Merge into this page:" : selectedPages.length ? "Merge into this page (your selection first):" : "Merge into this page (pages around it):"}</li>
            {pages.map((p, i) => (
              <li key={p.slug} role="option" aria-selected={i === pick}>
                <button type="button" className={cn("flex w-full items-baseline gap-2 rounded px-2 py-1 text-left hover:bg-accent", i === pick && "bg-accent")} onMouseDown={(e) => e.preventDefault()} onClick={() => send({ kind: "merge", target: p.slug })}>
                  <span>{p.title}</span>
                  <span className="ml-auto font-mono text-xs text-muted-foreground">{p.slug}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      {!disabled && (
        <div className="flex items-center gap-1" aria-label="Commands">
          {COMMANDS.map((c) => (
            <button key={c.name} type="button" disabled={!!busy} onClick={() => start(c.name)} className="flex items-baseline gap-1.5 rounded px-1.5 py-0.5 text-xs text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-50">
              <span className="font-mono text-foreground/80">{c.name}</span>
              <span>{COMMAND_HINT[c.name]}</span>
            </button>
          ))}
        </div>
      )}
      {error && (
        <p role="alert" className="text-xs text-bad">
          {error} Your note is kept.
        </p>
      )}
    </div>
  );
});
