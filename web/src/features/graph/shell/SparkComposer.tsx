import { Mic, Plus, SendHorizontal, Square, X } from "lucide-react";
import { useRef, useState, type FormEvent, type KeyboardEvent, type RefObject } from "react";
import { Button } from "@/components/ui/button";
import { link } from "@/lib/links";
import { cn } from "@/lib/utils";
import { useChatFull } from "./chatFullStore";
import { linkMentions, matchPages, openMention, withAttachments } from "./mentions";
import { marksContext } from "./replay";
import { useReplay } from "./replayStore";

const MAX_FILE = 200_000;
/** All files on one message together: more than this would swamp the model's context. */
export const MAX_ATTACHED = 500_000;

const readText = (f: File): Promise<string> =>
  typeof f.text === "function"
    ? f.text()
    : new Promise((resolve, reject) => {
        const r = new FileReader();
        r.onload = () => resolve(String(r.result ?? ""));
        r.onerror = () => reject(r.error);
        r.readAsText(f);
      });

interface Props {
  text: string;
  setText: (t: string) => void;
  busy: boolean;
  box: RefObject<HTMLTextAreaElement | null>;
  onSend: (text: string) => void;
  onStop: () => void;
  /** flag `chat-full`: attach files and mention pages with @ */
  rich: boolean;
}

/**
 * The composer of the chat panel. With `rich` (flag `chat-full`) the plus attaches text files (sent inline) and
 * typing `@` completes a page of the graph; a node clicked on the graph inserts its `@page` (see GraphScreen).
 */
export function SparkComposer({ text, setText, busy, box, onSend, onStop, rich }: Props) {
  const pages = useChatFull((s) => s.pages);
  const file = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<{ name: string; text: string }[]>([]);
  const [problem, setProblem] = useState("");
  const [idx, setIdx] = useState(0);
  const [dismissed, setDismissed] = useState("");
  // marks placed in a replay (a page the agent missed, a citation to re-check): chips here, context on the next send
  const missed = useReplay((s) => s.missed);
  const bad = useReplay((s) => s.bad);

  const mention = rich ? openMention(text) : null;
  const options = mention && dismissed !== text ? matchPages(pages, mention.query) : [];

  const insert = (id: string) => {
    if (!mention) return;
    setText(`${text.slice(0, mention.start)}@${id} `);
    setIdx(0);
    box.current?.focus();
  };

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    const q = text.trim();
    if (!q) return;
    const label = (id: string) => link(id, pages.find((p) => p.id === id)?.title || id);
    const context = busy ? "" : marksContext(missed, bad, label); // a send ignored while busy keeps the marks
    const body = rich ? withAttachments(linkMentions(q, pages), files) : q;
    onSend(context ? `${body}\n\n${context}` : body);
    if (!busy) useReplay.getState().clearMarks();
    setFiles([]);
    setProblem("");
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (options.length) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        setIdx((i) => (e.key === "ArrowDown" ? (i + 1) % options.length : (i - 1 + options.length) % options.length));
        return;
      }
      if ((e.key === "Enter" || e.key === "Tab") && !e.nativeEvent.isComposing) {
        e.preventDefault();
        insert(options[Math.min(idx, options.length - 1)]!.id);
        return;
      }
      if (e.key === "Escape") {
        // the list closes first; a second Escape reaches the panel
        e.preventDefault();
        e.stopPropagation();
        setDismissed(text);
        return;
      }
    }
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };

  const attach = async (list: FileList | null) => {
    if (!list) return;
    const added: { name: string; text: string }[] = [];
    let total = files.reduce((n, f) => n + f.text.length, 0);
    for (const f of Array.from(list)) {
      if (f.size > MAX_FILE) {
        setProblem(`${f.name} is larger than 200 KB; attach a text file under that.`);
        continue;
      }
      try {
        const t = await readText(f);
        if (t.includes("\u0000")) throw new Error("binary");
        if (total + t.length > MAX_ATTACHED) {
          setProblem(`${f.name} would take the attachments over 500 KB together; remove a file first.`);
          continue;
        }
        total += t.length;
        added.push({ name: f.name, text: t });
        setProblem("");
      } catch {
        setProblem(`${f.name} is not a text file; only text files can be attached.`);
      }
    }
    if (added.length) setFiles((cur) => [...cur, ...added]);
    if (file.current) file.current.value = "";
  };

  return (
    <div className="relative flex flex-col gap-1.5">
      {options.length > 0 && (
        <ul role="listbox" aria-label="Pages" data-testid="mention-list" className="absolute inset-x-0 bottom-full z-10 mb-1 overflow-hidden rounded-xl border bg-card py-1 shadow-[var(--shadow)]">
          {options.map((p, i) => (
            <li key={p.id} role="option" aria-selected={i === idx}>
              <button
                type="button"
                tabIndex={-1}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => insert(p.id)}
                className={cn("flex w-full items-center gap-2 px-3 py-1.5 text-left text-[13px]", i === idx ? "bg-secondary" : "hover:bg-secondary/60")}
              >
                <span className="min-w-0 flex-1 truncate">{p.title || p.id}</span>
                <small className="shrink-0 text-[11px] text-muted-foreground">@{p.id}</small>
              </button>
            </li>
          ))}
        </ul>
      )}
      {files.length > 0 && (
        <ul aria-label="Attached files" className="flex flex-wrap gap-1.5 px-1">
          {files.map((f, i) => (
            <li key={`${f.name}:${i}`} className="flex items-center gap-1 rounded-full bg-secondary py-0.5 pl-2.5 pr-1 text-xs">
              <span className="max-w-40 truncate">{f.name}</span>
              <button type="button" aria-label={`Remove ${f.name}`} className="grid size-5 place-items-center rounded-full hover:bg-background" onClick={() => setFiles((cur) => cur.filter((_, j) => j !== i))}>
                <X aria-hidden className="size-3" strokeWidth={1.8} />
              </button>
            </li>
          ))}
        </ul>
      )}
      {(missed.length > 0 || bad.length > 0) && (
        <ul aria-label="Marks from the replay" data-testid="replay-chips" className="flex flex-wrap gap-1.5 px-1">
          {[...missed.map((id) => ({ id, kind: "Missed" })), ...bad.map((id) => ({ id, kind: "Bad citation" }))].map((m) => {
            const name = pages.find((p) => p.id === m.id)?.title || m.id;
            return (
              <li key={`${m.kind}:${m.id}`} className="flex items-center gap-1 rounded-full bg-secondary py-0.5 pl-2.5 pr-1 text-xs">
                <span className="text-muted-foreground">{m.kind}</span>
                <span className="max-w-40 truncate">{name}</span>
                <button type="button" aria-label={`Remove the ${m.kind.toLowerCase()} mark on ${name}`} className="grid size-5 place-items-center rounded-full hover:bg-background" onClick={() => useReplay.getState().unmark(m.id)}>
                  <X aria-hidden className="size-3" strokeWidth={1.8} />
                </button>
              </li>
            );
          })}
        </ul>
      )}
      {problem && (
        <p role="alert" className="px-1 text-xs text-bad">
          {problem}
        </p>
      )}
      <form onSubmit={submit} className="flex items-end gap-1 rounded-[20px] border bg-background px-2 py-1.5 focus-within:ring-2 focus-within:ring-ring">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="size-8 shrink-0 rounded-full"
          aria-label="Attach"
          title={rich ? "Attach a text file" : "Attach, coming soon"}
          onClick={() => file.current?.click()}
          disabled={!rich}
        >
          <Plus aria-hidden strokeWidth={1.6} />
        </Button>
        {rich && <input ref={file} type="file" multiple accept="text/*,.md,.csv,.json,.tsv,.yaml,.yml,.toml,.py,.ts,.tex" className="hidden" aria-label="Attach files" data-testid="attach-input" onChange={(e) => void attach(e.target.files)} />}
        <textarea
          ref={box}
          rows={1}
          aria-label="Your message"
          placeholder={rich ? "Type / for commands, @ for a page" : "Type / for commands"}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setIdx(0);
          }}
          onKeyDown={onKey}
          className="max-h-32 min-h-8 min-w-0 flex-1 resize-none bg-transparent py-1.5 text-sm outline-none placeholder:text-muted-foreground"
        />
        <Button type="button" variant="ghost" size="icon" className="size-8 shrink-0 rounded-full" aria-label="Voice input" title="Voice input is not available yet" disabled>
          <Mic aria-hidden strokeWidth={1.6} />
        </Button>
        {busy ? (
          <Button type="button" variant="ghost" size="icon" className="size-8 shrink-0 rounded-full" aria-label="Stop" onClick={onStop}>
            <Square aria-hidden strokeWidth={1.6} />
          </Button>
        ) : (
          <Button type="submit" variant="ghost" size="icon" className="size-8 shrink-0 rounded-full" aria-label="Send" disabled={!text.trim()}>
            <SendHorizontal aria-hidden strokeWidth={1.6} />
          </Button>
        )}
      </form>
    </div>
  );
}
