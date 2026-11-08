import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { useDataSource, type ChatStatus, type ScopeList } from "@/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field, Select } from "./fields";
import { PastChats } from "./PastChats";
import { SkillsPanel } from "./SkillsPanel";
import { sessionIdOf } from "./serverStorage";
import { fmtUsd } from "./format";
import { ago, type SessionEntry } from "./sessions";
import { NeedsClaudeBadge } from "./NeedsClaudeBadge";
import { NEEDS_CLAUDE, authPayload, authValue, backendLabel, type StatusView } from "./status";

export const STATUS_KEY = ["chat", "status"] as const;

interface Props {
  status: StatusView;
  scopes: ScopeList["scopes"];
  model: string;
  onModel: (id: string) => void;
  scope: string;
  onScope: (slug: string) => void;
  /** agent mode: stored sessions that can be resumed (omitted = no list) */
  sessions?: SessionEntry[];
  activeId?: string;
  onResume?: (entry: SessionEntry) => void;
}

function Message({ error, ok }: { error?: Error | null; ok?: string }) {
  if (error) return <p role="alert" className="break-words text-xs text-bad">{error.message}</p>;
  return ok ? <p role="status" className="text-xs text-ok">{ok}</p> : null;
}

export function SessionPanel({ status, scopes, model, onModel, scope, onScope, sessions, activeId, onResume }: Props) {
  const ds = useDataSource();
  const qc = useQueryClient();
  const accept = (st: ChatStatus) => qc.setQueryData(STATUS_KEY, st);

  const settings = useMutation({ mutationFn: (b: Parameters<typeof ds.updateChatSettings>[0]) => ds.updateChatSettings(b), onSuccess: accept });
  const addKey = useMutation({ mutationFn: (b: { name: string; key: string }) => ds.addChatKey(b), onSuccess: accept });
  const removeKey = useMutation({ mutationFn: (name: string) => ds.removeChatKey(name), onSuccess: accept });

  const [keyName, setKeyName] = useState("");
  const [keyValue, setKeyValue] = useState("");
  const auth = authValue(status);
  const removable = auth.startsWith("key:") && auth !== "key:" && auth !== "key:env";
  const chip = backendLabel(status);
  const sub = status.subscription;
  const scopeRow = scopes.find((s) => s.slug === scope);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-1">
        <p className="flex items-center gap-2 text-sm font-medium">
          <span aria-hidden className={`size-2 rounded-full ${chip.ok ? "bg-ok" : "bg-bad"}`} />
          {chip.text}
        </p>
        {!status.keyLoaded && status.authMode !== "subscription" && (
          <p className="text-xs text-muted-foreground">
            No API key. Add one below, set <code>ANTHROPIC_API_KEY</code> or create <code>{status.keyFile}</code>.
          </p>
        )}
        {sub.loggedIn && sub.email && <p className="text-xs text-muted-foreground">{sub.email}</p>}
      </div>

      <Field
        label="Account"
        hint={
          auth === "subscription"
            ? "Agent backend only · counts against your plan, not the credit."
            : sub.loggedIn
              ? "Billed to the selected key. Your subscription is also available."
              : sub.error
                ? `Subscription: ${sub.error}`
                : undefined
        }
      >
        <Select
          value={auth}
          onChange={(e) => settings.mutate(authPayload(e.target.value))}
          aria-label="Account"
          title="Which credentials pay for the next message"
        >
          <option value="subscription" disabled={!sub.loggedIn}>
            {sub.loggedIn ? `Claude subscription — ${sub.plan ? sub.plan.toUpperCase() + " · " : ""}${sub.email || "logged in"}` : "Claude subscription — not logged in"}
          </option>
          {status.keys.map((k) => (
            <option key={k.name} value={`key:${k.name}`}>
              {k.name === "env" ? "API key — ANTHROPIC_API_KEY" : k.name === "default" ? "API key — default file" : `API key — ${k.name}`} ({k.hint})
            </option>
          ))}
          {!status.keys.length && <option value="key:" disabled>No API key stored yet</option>}
        </Select>
      </Field>
      <Message error={settings.error} />

      <details className="rounded-md border p-2 text-sm">
        <summary className="cursor-pointer text-xs font-medium">Add or remove an API key</summary>
        <form
          className="mt-2 flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            addKey.mutate({ name: keyName, key: keyValue }, { onSuccess: () => { setKeyName(""); setKeyValue(""); } });
          }}
        >
          <Field label="Name">
            <Input value={keyName} onChange={(e) => setKeyName(e.target.value)} placeholder="e.g. personal" maxLength={40} pattern="[a-z0-9\-]+" />
          </Field>
          <Field label="Key">
            <Input type="password" value={keyValue} onChange={(e) => setKeyValue(e.target.value)} placeholder="sk-ant-…" autoComplete="off" />
          </Field>
          <div className="flex gap-2">
            <Button type="submit" size="sm" disabled={addKey.isPending || !keyName || !keyValue}>Add and use</Button>
            <Button type="button" variant="ghost" size="sm" disabled={!removable || removeKey.isPending} onClick={() => removeKey.mutate(auth.slice(4))}>
              Remove selected
            </Button>
          </div>
          <Message error={addKey.error ?? removeKey.error} ok={addKey.isSuccess ? "Key stored and selected." : removeKey.isSuccess ? "Key removed." : undefined} />
          <p className="text-xs text-muted-foreground">
            Stored as files under <code>{status.keysDir || "~/.config/kb-distillery/keys/"}</code> and never leave this machine. Only the last four characters are shown.
          </p>
        </form>
      </details>

      {status.spend && <Budget key={`${status.keyName}|${status.spend.credit}|${status.resetDay}`} status={status} onSave={(b) => settings.mutate(b)} saving={settings.isPending} error={settings.error} />}

      <Field
        label="Backend"
        hint={
          <>
            {status.agentAvailable
              ? status.agentVersion
                ? `Claude Agent SDK ${status.agentVersion} · read-only over wiki/, raw/, think/`
                : undefined
              : `Agent backend unavailable: ${status.agentError || "SDK missing"}. Using Direct.`}
            {!status.claudeAvailable && (
              <span className="mt-1 flex flex-col items-start gap-1">
                <NeedsClaudeBadge reason={status.claudeReason} />
                <span>{status.claudeReason}</span>
              </span>
            )}
          </>
        }
      >
        <Select
          value={status.agentAvailable ? status.backend : "direct"}
          onChange={(e) => settings.mutate({ backend: e.target.value })}
          aria-label="Backend"
        >
          <option value="agent" disabled={!status.agentAvailable}>
            Agent — reads the vault itself{!status.claudeAvailable ? ` (${NEEDS_CLAUDE})` : ""}
          </option>
          <option value="direct">Direct — retrieval + one call</option>
        </Select>
      </Field>

      {sessions && onResume && <RecentSessions sessions={sessions} activeId={activeId} onResume={onResume} />}

      {activeId && <SkillsPanel sessionId={sessionIdOf(activeId)} />}

      <Field label="Model">
        <Select value={model} onChange={(e) => onModel(e.target.value)} aria-label="Model">
          {status.models.map((m) => (
            <option key={m.id} value={m.id}>{m.label}</option>
          ))}
        </Select>
      </Field>

      <Field
        label="Scope"
        hint={
          scope
            ? `Answers use only this scope's pages${scopeRow?.coverage != null ? ` (${Math.round(100 * scopeRow.coverage)}% digested)` : ""} and end with what is not yet digested.`
            : undefined
        }
      >
        <Select value={scope} onChange={(e) => onScope(e.target.value)} aria-label="Scope">
          <option value="">All knowledge</option>
          {scope && !scopeRow && <option value={scope}>{scope}</option>}
          {scopes.map((s) => (
            <option key={s.slug} value={s.slug}>
              {s.title || s.slug}
              {s.coverage != null ? ` · ${Math.round(100 * s.coverage)}% digested` : ""}
            </option>
          ))}
        </Select>
      </Field>

      <PastChats />
    </div>
  );
}

function RecentSessions({ sessions, activeId, onResume }: { sessions: SessionEntry[]; activeId?: string; onResume: (e: SessionEntry) => void }) {
  return (
    <div className="flex flex-col gap-1" aria-label="Recent sessions" role="group">
      <p className="text-xs font-medium">Recent sessions</p>
      {sessions.length === 0 ? (
        <p className="text-xs text-muted-foreground">Finished agent chats show up here and can be resumed.</p>
      ) : (
        <ul className="flex flex-col">
          {sessions.map((s) => (
            <li key={s.id}>
              <button
                type="button"
                onClick={() => onResume(s)}
                aria-current={s.id === activeId ? "true" : undefined}
                className="flex w-full flex-col rounded-md px-2 py-1 text-left hover:bg-accent aria-[current=true]:bg-accent"
              >
                <span className="truncate text-sm">{s.title}</span>
                <span className="text-xs text-muted-foreground">{ago(s.last)}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Budget({
  status,
  onSave,
  saving,
  error,
}: {
  status: StatusView;
  onSave: (b: { key_name: string; monthly_credit: number; reset_day: number }) => void;
  saving: boolean;
  error: Error | null;
}) {
  const s = status.spend!;
  const [name, setName] = useState(status.keyName);
  const [credit, setCredit] = useState(String(s.credit));
  const [day, setDay] = useState(String(status.resetDay));
  const used = s.credit > 0 ? Math.min(100, (s.spent / s.credit) * 100) : 0;
  const left = Math.max(0, s.left);
  const low = s.credit > 0 && left < s.credit * 0.1;
  const date = (d: string): ReactNode => (d ? new Date(d + "T00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "");
  return (
    <div className="flex flex-col gap-1 rounded-md border p-2 text-sm">
      <p>
        <strong className={low ? "text-bad" : undefined}>{fmtUsd(left)}</strong> <span className="text-muted-foreground">left (estimate)</span>
        {low && <Badge variant="bad" className="ml-2">low</Badge>}
      </p>
      <div role="progressbar" aria-label="Credit used this cycle" aria-valuenow={Math.round(used)} aria-valuemin={0} aria-valuemax={100} className="h-1.5 overflow-hidden rounded bg-muted">
        <div className="h-full bg-primary" style={{ width: `${used}%` }} />
      </div>
      <p className="text-xs text-muted-foreground">
        of ${s.credit} · spent {fmtUsd(s.spent)} in {s.turns} request{s.turns === 1 ? "" : "s"} since {date(s.cycleStart)} · resets {date(s.nextReset)}
        {s.subscriptionTurns ? ` · ${s.subscriptionTurns} on the subscription` : ""}
      </p>
      <p className="text-xs text-muted-foreground">
        Counts this app's requests only.{" "}
        <a className="text-primary underline" href="https://console.anthropic.com/settings/billing" target="_blank" rel="noopener noreferrer">Exact balance</a>.
      </p>
      <details>
        <summary className="cursor-pointer text-xs font-medium">Edit key name and credit</summary>
        <form
          className="mt-2 flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            onSave({ key_name: name, monthly_credit: Number(credit), reset_day: Number(day) });
          }}
        >
          <Field label="Key name"><Input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} /></Field>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Monthly credit ($)"><Input type="number" min={0} step={1} value={credit} onChange={(e) => setCredit(e.target.value)} /></Field>
            <Field label="Resets on day"><Input type="number" min={1} max={31} step={1} value={day} onChange={(e) => setDay(e.target.value)} /></Field>
          </div>
          <Button type="submit" size="sm" className="self-start" disabled={saving}>Save</Button>
          <Message error={error} />
        </form>
      </details>
    </div>
  );
}
