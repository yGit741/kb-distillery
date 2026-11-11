import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { AtSign, MessageCircle, MessageSquarePlus, PanelRightClose, Pencil, Quote, Send, X } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent, type ReactNode, type RefObject } from "react";
import { useDataSource } from "@/api";
import type { ChatMessage, MentionHit, PageChatReply } from "@/api/types";
import { Button } from "@/components/ui/button";
import { useVariant, VARIANTS } from "@/components/variants";
import { useApiQuery } from "@/lib/useApiQuery";
import { cn } from "@/lib/utils";
import { useFlag } from "@/flags/useFlag";
import { pageTo, usePageSearch } from "./parts";
import { SlashHints, useRestructureSlash } from "../restructure/entry";

export type SelectionChip = { block_at: number | null; text: string };
export const ENTRY_IDS = ["selection", "bubble", "gutter", "command", "rail"] as const;
export const BLOCKS = "p, li, h1, h2, h3, h4, h5, h6, blockquote, pre, td";
const RAIL_KEY = "kbd.page-chat.rail";

/** The article's text blocks (the page body; the header with title and badges is not a block). */
export function blocksOf(root: HTMLElement): Element[] {
  return Array.from(root.querySelectorAll(BLOCKS)).filter((el) => !el.closest("header"));
}

/** The index of the block that holds `node` among the article's text blocks, or null. */
export function blockIndexOf(root: HTMLElement | null, node: Node | null): number | null {
  if (!root || !node) return null;
  const el = (node.nodeType === Node.ELEMENT_NODE ? (node as Element) : node.parentElement)?.closest(BLOCKS);
  if (!el || !root.contains(el)) return null;
  const i = blocksOf(root).indexOf(el);
  return i < 0 ? null : i;
}

const clip = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

/** Shared state of one page's chat: open, the pending chips and a draft (entry points add to them). */
export function usePageChatState(slug: string) {
  const spec = VARIANTS["page-chat-entry"]!;
  const [entry] = useVariant("page-chat-entry", spec.options.map((o) => o.id), spec.default);
  const [open, setOpenRaw] = useState(() => {
    if (entry !== "rail") return false;
    try {
      return localStorage.getItem(RAIL_KEY) === "open";
    } catch {
      return false;
    }
  });
  const [chips, setChips] = useState<SelectionChip[]>([]);
  const [draft, setDraft] = useState("");
  const [mentions, setMentions] = useState<string[]>([]);
  const setOpen = useCallback(
    (v: boolean) => {
      setOpenRaw(v);
      if (entry === "rail") {
        try {
          localStorage.setItem(RAIL_KEY, v ? "open" : "closed");
        } catch {
          /* storage blocked: the rail forgets on reload */
        }
      }
    },
    [entry],
  );
  useEffect(() => {
    setChips([]);
    setMentions([]);
    setDraft("");
  }, [slug]);
  const addChip = useCallback((c: SelectionChip) => {
    const text = c.text.trim();
    if (text) setChips((cs) => (cs.some((x) => x.text === text) ? cs : [...cs, { block_at: c.block_at, text }]));
  }, []);
  const addMention = useCallback((slug: string) => setMentions((ms) => (ms.includes(slug) ? ms : [...ms, slug])), []);
  return { entry, open, setOpen, chips, setChips, addChip, draft, setDraft, mentions, setMentions, addMention };
}
export type PageChatState = ReturnType<typeof usePageChatState>;

/** The small header piece some entries add: an Edit button (selection) or a key hint (command). */
export function PageChatHeader({ chat }: { chat: PageChatState }) {
  if (chat.entry === "selection")
    return (
      <Button variant="outline" size="sm" aria-label="Edit this page" title="Say what to change; the edits come back for you to review" onClick={() => chat.setOpen(true)}>
        <Pencil aria-hidden /> Edit
      </Button>
    );
  if (chat.entry === "command")
    return (
      <span className="text-xs text-muted-foreground" title="Open the page command bar">
        <kbd className="rounded border px-1 font-mono text-[0.7rem]">/</kbd> to ask
      </span>
    );
  return null;
}

/** The entry point (by variant) plus the one panel every variant opens. */
export function PageChat({ slug, chat, articleRef }: { slug: string; chat: PageChatState; articleRef: RefObject<HTMLElement | null> }) {
  const ask = (c: SelectionChip) => {
    chat.addChip(c);
    chat.setOpen(true);
  };
  return (
    <>
      {chat.entry === "bubble" && !chat.open && (
        <button
          type="button"
          onClick={() => chat.setOpen(true)}
          className="fixed bottom-6 right-6 z-30 inline-flex items-center gap-2 rounded-full border bg-card px-4 py-2 text-sm text-foreground shadow-sm transition-colors hover:bg-muted"
        >
          <MessageCircle className="size-4" aria-hidden /> Ask about this page
        </button>
      )}
      {chat.entry === "gutter" && <GutterMarks articleRef={articleRef} onAsk={ask} />}
      {chat.entry === "command" && <CommandBar chat={chat} />}
      {chat.entry === "rail" && !chat.open && (
        <button
          type="button"
          onClick={() => chat.setOpen(true)}
          aria-label="Discuss this page"
          className="fixed right-0 top-1/3 z-30 flex w-8 flex-col items-center gap-2 rounded-l-md border border-r-0 bg-card py-4 text-xs text-muted-foreground shadow-sm hover:text-foreground"
        >
          <MessageCircle className="size-4" aria-hidden />
          <span className="[writing-mode:vertical-rl]">Discuss</span>
        </button>
      )}
      {chat.open && <ChatPanel slug={slug} chat={chat} />}
    </>
  );
}

function GutterMarks({ articleRef, onAsk }: { articleRef: RefObject<HTMLElement | null>; onAsk: (c: SelectionChip) => void }) {
  const [hover, setHover] = useState<{ top: number; el: Element; i: number } | null>(null);
  useEffect(() => {
    const root = articleRef.current;
    if (!root) return;
    const onMove = (e: MouseEvent) => {
      const el = (e.target as Element | null)?.closest?.(BLOCKS);
      if (!el || !root.contains(el) || el.closest("header")) return;
      const i = blocksOf(root).indexOf(el);
      const top = el.getBoundingClientRect().top - root.getBoundingClientRect().top;
      setHover((h) => (h?.el === el ? h : { top, el, i }));
    };
    const onLeave = () => setHover(null);
    root.addEventListener("mousemove", onMove);
    root.addEventListener("mouseleave", onLeave);
    return () => {
      root.removeEventListener("mousemove", onMove);
      root.removeEventListener("mouseleave", onLeave);
    };
  }, [articleRef]);
  if (!hover) return null;
  return (
    <button
      type="button"
      aria-label="Ask about this block"
      title="Ask about this block"
      onClick={() => onAsk({ block_at: hover.i, text: clip(hover.el.textContent ?? "", 400) })}
      className="absolute -right-7 z-10 rounded p-1 text-muted-foreground/70 hover:bg-muted hover:text-foreground"
      style={{ top: hover.top }}
    >
      <MessageSquarePlus className="size-4" aria-hidden />
    </button>
  );
}

function CommandBar({ chat }: { chat: PageChatState }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [mode, setMode] = useState<"ask" | "mention">("ask");
  const hits = useMentionSearch(mode === "mention" && open ? q : null);
  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      const typing = !!t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable);
      if (((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") || (e.key === "/" && !typing && !e.metaKey && !e.ctrlKey)) {
        e.preventDefault();
        e.stopImmediatePropagation(); // on a page in this variant the page bar owns the key, not the app palette
        setOpen((o) => !o);
        setMode("ask");
        setQ("");
      } else if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, []);
  if (!open) return null;
  const close = () => setOpen(false);
  const items: { label: ReactNode; run: () => void }[] =
    mode === "ask"
      ? [
          { label: <>Ask about this page{q ? <span className="text-muted-foreground">: {clip(q, 60)}</span> : ""}</>, run: () => (chat.setDraft(q), chat.setOpen(true), close()) },
          { label: "Mention a page…", run: () => (setMode("mention"), setQ("")) },
          { label: "Open chat", run: () => (chat.setOpen(true), close()) },
        ]
      : hits.map((h) => ({ label: <>@{h.slug} <span className="text-muted-foreground">{h.title}</span></>, run: () => (chat.addMention(h.slug), chat.setOpen(true), close()) }));
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-background/40 pt-[18vh]" onMouseDown={close}>
      <div role="dialog" aria-label="Page command bar" className="w-[32rem] max-w-[92vw] rounded-lg border bg-card shadow-md" onMouseDown={(e) => e.stopPropagation()}>
        <input
          autoFocus
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && items[0]) {
              e.preventDefault();
              items[0].run();
            }
          }}
          placeholder={mode === "ask" ? "Ask about this page…" : "Find a page to mention…"}
          className="w-full border-b bg-transparent px-3 py-2.5 text-sm outline-none"
        />
        <ul className="p-1">
          {items.map((it, i) => (
            <li key={i}>
              <button type="button" onClick={it.run} className="w-full rounded px-2 py-1.5 text-left text-sm hover:bg-muted">
                {it.label}
              </button>
            </li>
          ))}
          {items.length === 0 && <li className="px-2 py-1.5 text-sm text-muted-foreground">No page matches.</li>}
        </ul>
      </div>
    </div>
  );
}

function useMentionSearch(q: string | null): MentionHit[] {
  const q2 = q ?? "";
  const res = useApiQuery<MentionHit[]>(["pages", "mentions", q2], (ds) => ds.searchMentions(q2), {
    enabled: q !== null,
    retry: false,
    staleTime: 60_000,
  });
  return q === null ? [] : (res.data ?? []);
}

type Local = ChatMessage & { local?: boolean };

/** The one chat panel (a right drawer); every entry variant opens this. */
export function ChatPanel({ slug, chat }: { slug: string; chat: PageChatState }) {
  const ds = useDataSource();
  const qc = useQueryClient();
  const thread = useApiQuery(["pages", "chat", slug], (d) => d.getPageChat(slug), { retry: false });
  const [local, setLocal] = useState<Local[]>([]);
  const [error, setError] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const send = useMutation({
    mutationFn: (body: { message: string; selections: SelectionChip[]; mentions: string[] }) => ds.postPageChat(slug, body),
    onMutate: (body) => {
      setError(null);
      setLocal((l) => [...l, { role: "user", text: body.message, at: "", selections: body.selections, mentions: body.mentions, proposal_id: null, hunks: 0, skipped: [], unknown_mentions: [], local: true }]);
    },
    onSuccess: (r: PageChatReply) => {
      setLocal((l) => [...l, { role: "assistant", text: r.reply, at: "", selections: [], mentions: [], proposal_id: r.proposal_id ?? null, hunks: r.hunks, skipped: r.skipped, unknown_mentions: r.unknown_mentions, local: true }]);
      chat.setChips([]);
      chat.setMentions([]);
      chat.setDraft("");
      void qc.invalidateQueries({ queryKey: ["proposals"] });
    },
    onError: (e) => {
      setLocal((l) => l.slice(0, -1));
      setError(e instanceof Error ? e.message : String(e));
    },
  });
  const messages: Local[] = [...(thread.data?.messages ?? []), ...local];
  useLayoutEffect(() => {
    listRef.current?.scrollTo?.({ top: listRef.current.scrollHeight });
  }, [messages.length]);

  return (
    <aside aria-label="Page chat" className="fixed bottom-0 right-0 top-0 z-40 flex w-[26rem] max-w-[100vw] flex-col border-l bg-background shadow-lg">
      <header className="flex items-center justify-between border-b px-4 py-3">
        <h2 className="text-sm font-medium">{chat.entry === "selection" ? "Edit this page" : "Discuss this page"}</h2>
        <Button variant="ghost" size="sm" aria-label="Close chat" onClick={() => chat.setOpen(false)}>
          <PanelRightClose />
        </Button>
      </header>
      <div ref={listRef} className="flex flex-1 flex-col gap-3 overflow-y-auto px-4 py-3">
        {messages.length === 0 && (
          <p className="text-sm text-muted-foreground">
            Ask for a change, point at a passage, or mention a page with @. Edits come back as a proposal you review; nothing changes the page directly.
          </p>
        )}
        {messages.map((m, i) => (
          <Message key={i} m={m} slug={slug} />
        ))}
        {send.isPending && <p className="text-sm text-muted-foreground">Thinking…</p>}
      </div>
      <Composer
        chat={chat}
        pending={send.isPending}
        error={error}
        onSend={(body) => send.mutate(body)}
      />
    </aside>
  );
}

function Message({ m, slug }: { m: Local; slug: string }) {
  // flag ui.page-review: the proposal opens in this page, not on the separate review screen
  const inPage = useFlag("ui.page-review");
  const search = usePageSearch() as Record<string, string>;
  if (m.role === "user")
    return (
      <div className="ml-8 rounded-lg bg-muted px-3 py-2 text-sm">
        {m.selections.map((s, i) => (
          <p key={i} className="mb-1 border-l-2 pl-2 text-xs text-muted-foreground">“{clip(s.text, 120)}”</p>
        ))}
        <p className="whitespace-pre-wrap">{m.text}</p>
        {m.mentions.length > 0 && <p className="mt-1 text-xs text-muted-foreground">{m.mentions.map((s) => `@${s}`).join(" ")}</p>}
      </div>
    );
  return (
    <div className="mr-8 flex flex-col gap-2 text-sm">
      <p className="whitespace-pre-wrap">{m.text}</p>
      {m.proposal_id && (
        <Link
          to={inPage ? pageTo(slug) : (`/proposals/${encodeURIComponent(m.proposal_id)}` as "/")}
          search={(inPage ? { ...search, review: m.proposal_id } : {}) as never}
          className="rounded-lg border bg-card px-3 py-2 hover:bg-muted"
          data-testid="proposal-card"
        >
          <span className="font-medium">Proposal</span>
          <span className="text-muted-foreground">
            : {m.hunks} hunk{m.hunks === 1 ? "" : "s"}, {m.skipped.length} skipped
          </span>
          <span className="block text-xs text-muted-foreground">Review what would change</span>
        </Link>
      )}
      {!m.proposal_id && m.skipped.length > 0 && <p className="text-xs text-muted-foreground">{m.skipped.length} suggested edit{m.skipped.length === 1 ? "" : "s"} skipped.</p>}
      {m.skipped.map((s, i) => (
        <p key={i} className="text-xs text-muted-foreground">Skipped “{clip(s.before, 60)}”: {s.reason}</p>
      ))}
      {m.unknown_mentions.length > 0 && <p className="text-xs text-muted-foreground">Not found: {m.unknown_mentions.map((s) => `@${s}`).join(", ")}</p>}
    </div>
  );
}

/** The composer: chips for selections and mentions, @ opens the picker, Enter sends, Shift+Enter is a newline. */
export function Composer({
  chat,
  pending,
  error,
  onSend,
}: {
  chat: Pick<PageChatState, "chips" | "setChips" | "draft" | "setDraft" | "mentions" | "setMentions" | "addMention">;
  pending: boolean;
  error: string | null;
  onSend: (body: { message: string; selections: SelectionChip[]; mentions: string[] }) => void;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const [cursor, setCursor] = useState(0);
  const [pick, setPick] = useState(0);
  const at = /(^|\s)@([\w-]*)$/.exec(chat.draft.slice(0, cursor));
  const query = at ? at[2]! : null;
  const hits = useMentionSearch(query);
  const picking = query !== null && hits.length > 0;
  const restructure = useRestructureSlash();
  useEffect(() => setPick(0), [query]);

  const insert = (slug: string) => {
    if (!at) return;
    const start = cursor - at[2]!.length - 1;
    const next = chat.draft.slice(0, start) + chat.draft.slice(cursor);
    chat.setDraft(next);
    chat.addMention(slug);
    setCursor(start);
    requestAnimationFrame(() => ref.current?.setSelectionRange(start, start));
  };
  const submit = () => {
    const message = chat.draft.trim();
    if (!message || pending) return;
    if (restructure.run(message, chat.mentions)) {
      chat.setDraft("");
      chat.setMentions([]);
      return;
    }
    onSend({ message, selections: chat.chips, mentions: chat.mentions });
  };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (picking) {
      if (e.key === "ArrowDown") return (e.preventDefault(), setPick((p) => (p + 1) % hits.length));
      if (e.key === "ArrowUp") return (e.preventDefault(), setPick((p) => (p - 1 + hits.length) % hits.length));
      if (e.key === "Enter" || e.key === "Tab") return (e.preventDefault(), insert(hits[pick]!.slug));
    }
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };
  const hasChips = chat.chips.length > 0 || chat.mentions.length > 0;
  return (
    <div className="relative border-t px-4 py-3">
      {picking && (
        <ul role="listbox" aria-label="Mention a page" className="absolute bottom-full left-4 right-4 mb-1 max-h-56 overflow-y-auto rounded-md border bg-card p-1 shadow-md">
          {hits.map((h, i) => (
            <li
              key={h.slug}
              role="option"
              aria-selected={i === pick}
              onMouseDown={(e) => (e.preventDefault(), insert(h.slug))}
              className={cn("cursor-pointer rounded px-2 py-1 text-sm", i === pick && "bg-muted")}
            >
              @{h.slug} <span className="text-xs text-muted-foreground">{h.title}</span>
            </li>
          ))}
        </ul>
      )}
      {restructure.enabled && !picking && <SlashHints draft={chat.draft} onPick={(k) => chat.setDraft(`/${k} `)} />}
      {hasChips && (
        <div className="mb-2 flex flex-wrap gap-1.5">
          {chat.chips.map((c, i) => (
            <span key={`s${i}`} className="inline-flex max-w-full items-center gap-1 rounded-md border bg-muted/60 px-2 py-0.5 text-xs" data-testid="selection-chip">
              <Quote className="size-3 shrink-0 text-muted-foreground" aria-hidden />
              <span className="truncate">“{clip(c.text, 48)}”</span>
              {c.block_at !== null && <span className="shrink-0 text-muted-foreground">block {c.block_at}</span>}
              <button type="button" aria-label="Remove selection" className="shrink-0 rounded hover:text-foreground" onClick={() => chat.setChips(chat.chips.filter((_, j) => j !== i))}>
                <X className="size-3" />
              </button>
            </span>
          ))}
          {chat.mentions.map((s) => (
            <span key={`m${s}`} className="inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs" data-testid="mention-chip">
              <AtSign className="size-3 text-muted-foreground" aria-hidden />
              {s}
              <button type="button" aria-label={`Remove @${s}`} className="rounded hover:text-foreground" onClick={() => chat.setMentions(chat.mentions.filter((x) => x !== s))}>
                <X className="size-3" />
              </button>
            </span>
          ))}
        </div>
      )}
      <div className="flex items-end gap-2">
        <textarea
          ref={ref}
          aria-label="Message"
          rows={2}
          value={chat.draft}
          onChange={(e) => {
            chat.setDraft(e.target.value);
            setCursor(e.target.selectionStart ?? e.target.value.length);
          }}
          onSelect={(e) => setCursor(e.currentTarget.selectionStart ?? 0)}
          onKeyDown={onKey}
          placeholder="Soften this, check against @a-page…"
          className="min-h-[2.5rem] flex-1 resize-none rounded-md border bg-background px-3 py-2 text-sm outline-none focus-visible:ring-1 focus-visible:ring-ring"
        />
        <Button size="sm" aria-label="Send" disabled={pending || !chat.draft.trim()} onClick={submit}>
          <Send />
        </Button>
      </div>
      {error && <p role="alert" className="mt-2 text-xs text-muted-foreground">That did not go through: {error}. Your message is still here; try again.</p>}
    </div>
  );
}
