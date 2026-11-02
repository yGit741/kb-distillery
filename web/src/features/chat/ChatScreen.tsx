import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearch } from "@tanstack/react-router";
import { Download, PanelRightOpen, Plus, SendHorizontal, Square } from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent, type KeyboardEvent } from "react";
import { useDataSource } from "@/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ErrorState, Loading } from "@/components/states";
import type { SearchById } from "@/routes/search";
import { MessageList, Sources } from "./MessageList";
import { PromptPanel } from "./PromptPanel";
import { STATUS_KEY, SessionPanel } from "./SessionPanel";
import { isCustom, parsePrompts, pick, setEdit, systemFor, type Edits } from "./prompts";
import { authPayload, authValue, backendLabel, effectiveBackend, parseStatus } from "./status";
import { readJson, writeJson } from "./storage";
import { canSave, chatTitle, savableMessages } from "./thread";
import { useChatSession, type SendOptions } from "./useChatSession";

const EXAMPLES: { q: string; template?: string; label: string }[] = [
  { q: "What do I know about implicit regularization in matrix factorization?", label: "Implicit regularization in matrix factorization" },
  { q: "Which open questions in my notes could become a research topic?", template: "brainstorm", label: "Open questions that could be a topic" },
  { q: "Teach me tensor rank from my notes.", template: "learn", label: "Teach me tensor rank" },
];

/** `question` / `scope` override the URL's `?q` / `?scope` (the graph's chat dock passes them). */
export function ChatScreen({ question, scope }: { question?: string; scope?: string } = {}) {
  const ds = useDataSource();
  const qc = useQueryClient();
  const search = useSearch({ strict: false }) as SearchById["chat"];
  const status = useQuery({ queryKey: STATUS_KEY, queryFn: () => ds.getChatStatus() });
  const promptsQ = useQuery({ queryKey: ["chat", "prompts"], queryFn: () => ds.getChatPrompts() });
  const scopesQ = useQuery({ queryKey: ["scopes"], queryFn: () => ds.listScopes() });

  if (status.isPending || promptsQ.isPending) return <Loading label="Loading chat" rows={4} />;
  if (status.isError || promptsQ.isError) {
    return (
      <ErrorState
        title="The chat service is unreachable"
        error={status.error ?? promptsQ.error}
        onRetry={() => {
          void qc.invalidateQueries({ queryKey: ["chat"] });
        }}
      />
    );
  }
  return (
    <ChatBody
      status={status.data}
      prompts={promptsQ.data.prompts}
      scopes={scopesQ.data?.scopes ?? []}
      initialScope={scope ?? search.scope ?? ""}
      initialQuestion={question ?? search.q ?? ""}
    />
  );
}

interface BodyProps {
  status: Awaited<ReturnType<ReturnType<typeof useDataSource>["getChatStatus"]>>;
  prompts: Awaited<ReturnType<ReturnType<typeof useDataSource>["getChatPrompts"]>>["prompts"];
  scopes: Awaited<ReturnType<ReturnType<typeof useDataSource>["listScopes"]>>["scopes"];
  initialScope: string;
  initialQuestion: string;
}

function ChatBody({ status: rawStatus, prompts: rawPrompts, scopes, initialScope, initialQuestion }: BodyProps) {
  const ds = useDataSource();
  const view = useMemo(() => parseStatus(rawStatus), [rawStatus]);
  const prompts = useMemo(() => parsePrompts(rawPrompts), [rawPrompts]);
  const { chat, busy, send, regenerate, stop, reset, forgetSession } = useChatSession();

  const [templateId, setTemplateId] = useState(() => readJson("local", "kbchat.template", "query"));
  const [edits, setEdits] = useState<Edits>(() => readJson("local", "kbchat.edits", {}));
  const [modelPick, setModelPick] = useState(() => readJson("local", "kbchat.model", ""));
  const [scope, setScope] = useState(initialScope);
  const [question, setQuestion] = useState(initialQuestion);
  // a new question handed in from outside (the graph's "/" ask) replaces the draft, keeping the history
  useEffect(() => {
    if (initialQuestion) setQuestion(initialQuestion);
  }, [initialQuestion]);
  const [railOpen, setRailOpen] = useState(false);
  const [note, setNote] = useState<{ text: string; bad: boolean } | null>(null);
  const [saving, setSaving] = useState(false);

  const current = pick(prompts, templateId);
  const model = view.models.some((m) => m.id === modelPick) ? modelPick : view.defaultModel;
  const chip = backendLabel(view);

  const options = (): SendOptions => ({
    model,
    backend: effectiveBackend(view),
    scope,
    system: systemFor(current, edits),
    auth: authPayload(authValue(view)),
    label: `${current?.title ?? templateId}${isCustom(current, edits) ? " (custom)" : ""}`,
  });

  const selectTemplate = (id: string) => {
    setTemplateId(id);
    writeJson("local", "kbchat.template", id);
  };
  const edit = (text: string) => {
    if (!current) return;
    const next = setEdit(current, edits, text);
    setEdits(next);
    writeJson("local", "kbchat.edits", next);
  };
  const reseat = () => {
    if (!current) return;
    const next = { ...edits };
    delete next[current.id];
    setEdits(next);
    writeJson("local", "kbchat.edits", next);
  };

  const ask = (q: string) => {
    send(q, options());
    setQuestion("");
  };
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    ask(question);
  };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      ask(question);
    }
  };

  const save = async () => {
    setSaving(true);
    try {
      const out = await ds.saveChat({
        id: chat.id,
        title: chatTitle(chat.messages),
        model,
        template: templateId,
        custom: isCustom(current, edits),
        system: systemFor(current, edits),
        messages: savableMessages(chat.messages),
      });
      setNote({ text: `Saved to ${out.path}`, bad: false });
    } catch (e) {
      setNote({ text: `Save failed: ${e instanceof Error ? e.message : String(e)}`, bad: true });
    } finally {
      setSaving(false);
    }
  };

  const rail = (
    <div className="flex flex-col gap-4">
      <Card>
        <CardContent className="flex flex-col gap-3 p-3">
          <h2 className="text-sm font-semibold">Session</h2>
          <SessionPanel
            status={view}
            scopes={scopes}
            model={model}
            onModel={(id) => {
              setModelPick(id);
              writeJson("local", "kbchat.model", id);
            }}
            scope={scope}
            onScope={(slug) => {
              setScope(slug);
              forgetSession();
            }}
          />
        </CardContent>
      </Card>
      <Card>
        <CardContent className="flex flex-col gap-2 p-3">
          <h2 className="text-sm font-semibold">Sources this turn</h2>
          <Sources messages={chat.messages} />
        </CardContent>
      </Card>
    </div>
  );

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_20rem]">
      <section className="flex min-w-0 flex-col gap-3" aria-label="Chat">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-lg font-semibold">Chat</h1>
          <span className="inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs" data-testid="backend-chip">
            <span aria-hidden className={`size-2 rounded-full ${chip.ok ? "bg-ok" : "bg-bad"}`} />
            {chip.text}
          </span>
          {scope && <span className="rounded-md bg-accent-soft px-2 py-0.5 text-xs text-primary">scope: {scope}</span>}
          <div className="ml-auto flex gap-1">
            <Button variant="ghost" size="sm" className="lg:hidden" onClick={() => setRailOpen((o) => !o)} aria-expanded={railOpen}>
              <PanelRightOpen aria-hidden /> Session
            </Button>
            <Button variant="ghost" size="sm" onClick={save} disabled={saving || busy || !canSave(chat.messages)} title="Save this chat to raw/inbox/ as an LLM chat">
              <Download aria-hidden /> Save to inbox
            </Button>
            <Button variant="ghost" size="sm" onClick={reset} disabled={!chat.messages.length && !busy}>
              <Plus aria-hidden /> New chat
            </Button>
          </div>
        </div>
        {railOpen && <div className="lg:hidden">{rail}</div>}
        {note && (
          <p role={note.bad ? "alert" : "status"} className={`break-words text-sm ${note.bad ? "text-bad" : "text-ok"}`}>
            {note.text}
          </p>
        )}

        {chat.messages.length === 0 ? (
          <div className="flex flex-col gap-3 py-6">
            <h2 className="text-xl font-semibold">Chat with your knowledge base</h2>
            <p className="max-w-prose text-sm text-muted-foreground">
              In <strong>Agent</strong> mode Claude searches and reads your wiki itself (read-only) and shows every page it opened. <strong>Direct</strong> mode
              sends the top retrieved pages in one call. Answers cite pages as links to the page view.
            </p>
            <div className="flex flex-wrap gap-2">
              {EXAMPLES.map((ex) => (
                <Button
                  key={ex.q}
                  variant="outline"
                  size="sm"
                  className="h-auto whitespace-normal py-1.5 text-left"
                  onClick={() => {
                    if (ex.template) selectTemplate(ex.template);
                    send(ex.q, { ...options(), system: systemFor(pick(prompts, ex.template ?? templateId), edits) });
                  }}
                >
                  {ex.label}
                </Button>
              ))}
            </div>
          </div>
        ) : (
          <MessageList messages={chat.messages} busy={busy} onRegenerate={() => regenerate(options())} />
        )}

        <div className="sticky bottom-0 -mx-4 flex flex-col gap-2 border-t bg-background/95 px-4 py-3 backdrop-blur">
          <PromptPanel prompts={prompts} current={current} edits={edits} onTemplate={selectTemplate} onEdit={edit} onReset={reseat} />
          <form className="flex items-end gap-2" onSubmit={onSubmit}>
            <textarea
              className="min-h-[2.75rem] flex-1 resize-y rounded-md border bg-background p-2 text-sm"
              rows={2}
              aria-label="Your message"
              placeholder="Ask your knowledge base…  (Enter to send, Shift+Enter for a new line)"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={onKey}
            />
            {busy ? (
              <Button type="button" variant="secondary" onClick={stop}>
                <Square aria-hidden /> Stop
              </Button>
            ) : (
              <Button type="submit" disabled={!question.trim()}>
                <SendHorizontal aria-hidden /> Send
              </Button>
            )}
          </form>
        </div>
      </section>
      <aside className="hidden lg:block" aria-label="Session and sources">
        {rail}
      </aside>
    </div>
  );
}
