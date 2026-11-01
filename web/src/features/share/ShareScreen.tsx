import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { CopyButton } from "@/components/CopyButton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Empty, ErrorState, Loading } from "@/components/states";
import { useApiQuery } from "@/lib/useApiQuery";
import { createAdminClient, explain, type AdminClient, type Online, type PrunePlan, type Snapshot } from "./adminApi";
import {
  NAME_RE,
  PRUNE_APPLY,
  SETUP_COMMAND,
  historyCommand,
  rollbackCommand,
  snapshotCommand,
  validName,
  versionOptions,
} from "./commands";

const Code = ({ children }: { children: ReactNode }) => (
  <code className="rounded bg-muted px-1 py-0.5 font-mono text-[0.85em] break-all">{children}</code>
);

function OnlineBadge({ v }: { v: Online }) {
  return v === true ? <Badge variant="ok">online</Badge> : v === false ? <Badge variant="bad">down</Badge> : <Badge variant="warn">unknown</Badge>;
}

function BehindBadge({ n }: { n: number | null }) {
  if (n == null) return <Badge variant="outline" title="different schema version or unknown">?</Badge>;
  return n === 0 ? <Badge variant="ok">up to date</Badge> : <Badge variant="warn">{n} behind</Badge>;
}

function Setup({ message }: { message: string }) {
  return (
    <Card role="alert" className="border-warn">
      <CardContent className="flex flex-col gap-2 p-4 text-sm">
        <p className="font-medium text-warn">{message}</p>
        <p>
          One-time setup: create a Cloudflare API token with Account, Workers Scripts, Edit and Account, Account Analytics, Read,
          copy it, then in the repo run:
        </p>
        <pre className="overflow-x-auto rounded bg-muted p-2 text-xs">{SETUP_COMMAND}</pre>
        <p className="text-muted-foreground">Then reload this page. See the share-kb skill for details.</p>
      </CardContent>
    </Card>
  );
}

/** Type-the-name confirmation; the Worker requires {"confirm": "<worker>"} anyway. */
function DeleteDialog({
  worker,
  onClose,
  onConfirm,
  pending,
  error,
}: {
  worker: string | null;
  onClose: () => void;
  onConfirm: (worker: string, typed: string) => void;
  pending: boolean;
  error: string | null;
}) {
  const [typed, setTyped] = useState("");
  return (
    <Dialog
      open={worker !== null}
      onOpenChange={(o) => {
        if (!o) {
          setTyped("");
          onClose();
        }
      }}
    >
      <DialogContent>
        <div className="flex flex-col gap-3 p-4">
          <DialogTitle className="text-base font-semibold">Delete snapshot</DialogTitle>
          <DialogDescription className="text-sm">
            This removes the Worker and its link for everyone. Type <Code>{worker}</Code> to confirm.
          </DialogDescription>
          <Input aria-label="Type the snapshot name" value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" spellCheck={false} autoFocus />
          {error && <p role="alert" className="text-sm text-bad">{error}</p>}
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={onClose}>Cancel</Button>
            <Button
              className="bg-bad text-white"
              disabled={pending || !worker || typed !== worker}
              onClick={() => worker && onConfirm(worker, typed)}
            >
              {pending ? "Deleting" : "Delete"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function PruneBanner({ plan }: { plan: PrunePlan }) {
  const parts: ReactNode[] = [];
  if (plan.orphans.length)
    parts.push(
      <div key="o" className="flex flex-col gap-1">
        <p><strong>Orphans:</strong> {plan.orphans.join(", ")}. Snapshot Workers with no reachable manifest.</p>
        <p className="flex flex-wrap items-center gap-2">
          Remove them from the Mac: <Code>{PRUNE_APPLY}</Code> <CopyButton text={PRUNE_APPLY} label="Copy prune command" />
        </p>
      </div>,
    );
  if (plan.unknown.length) parts.push(<p key="u"><strong>Not answering:</strong> {plan.unknown.join(", ")} (manifest timed out, left alone).</p>);
  if (plan.foreign.length) parts.push(<p key="f"><strong>Not ours:</strong> {plan.foreign.join(", ")}. Other Workers in the account, never touched.</p>);
  if (!parts.length) return <p className="text-sm text-muted-foreground" data-testid="prune-clean">Prune check: nothing to clean up ({plan.ok.length} snapshot(s) answering).</p>;
  return (
    <Card role="status" className="border-warn" data-testid="prune-plan">
      <CardContent className="flex flex-col gap-2 p-3 text-sm">{parts}</CardContent>
    </Card>
  );
}

function SnapshotRow({
  s,
  onUpdate,
  onDelete,
}: {
  s: Snapshot;
  onUpdate: (s: Snapshot) => void;
  onDelete: (worker: string) => void;
}) {
  return (
    <tr className="border-t align-top">
      <td className="py-2 pr-4">
        <div className="font-medium">{s.name}</div>
        <div className="font-mono text-xs text-muted-foreground">{s.worker}</div>
      </td>
      <td className="py-2 pr-4 font-mono text-xs">
        {s.kb_version ? `kb-${s.kb_version}` : "none"}
        {s.content_sha && <div className="text-muted-foreground">{s.content_sha.slice(0, 7)}</div>}
      </td>
      <td className="py-2 pr-4"><BehindBadge n={s.behind_main} /></td>
      <td className="py-2 pr-4 text-right tabular-nums">{s.views_7d}</td>
      <td className="py-2 pr-4 font-mono text-xs">{s.built_at ? s.built_at.slice(0, 10) : "none"}</td>
      <td className="py-2 pr-4"><OnlineBadge v={s.online} /></td>
      <td className="py-2">
        <div className="flex flex-wrap gap-1">
          <Button asChild variant="secondary" size="sm">
            <a href={s.url} target="_blank" rel="noopener noreferrer" aria-label={`Open ${s.name}`}>Open</a>
          </Button>
          <CopyButton text={s.url} label="Copy link" />
          <Button variant="secondary" size="sm" title="Serve another knowledge version at this same link" onClick={() => onUpdate(s)}>
            Update
          </Button>
          <Button variant="outline" size="sm" className="text-bad" onClick={() => onDelete(s.worker)} aria-label={`Delete ${s.name}`}>
            Delete
          </Button>
        </div>
      </td>
    </tr>
  );
}

/** Builds `pixi run share -- snapshot <name> <kb-tag> [--replace]`: creating is a CLI step (it audits the public build). */
function NewSnapshot({
  known,
  draft,
  onDraft,
}: {
  known: ReadonlySet<string>;
  draft: { name: string; replace: boolean };
  onDraft: (d: { name: string; replace: boolean }) => void;
}) {
  const life = useApiQuery(["share", "versions"], (ds) => ds.getLifecycle(), { retry: false });
  const options = useMemo(() => versionOptions(life.data?.timeline ?? []), [life.data]);
  const [picked, setPicked] = useState("");
  const version = picked || options[0]?.tag || "";
  const [free, setFree] = useState("");
  const tag = options.length ? version : free.trim();
  const name = draft.name.trim().toLowerCase();
  const ok = validName(name);
  const exists = known.has(name);
  const hint =
    name && !ok
      ? "lowercase letters, digits and inner hyphens; not kb"
      : exists && !draft.replace
        ? "a snapshot with this name exists: tick update in place to replace it"
        : "";
  const cmd = snapshotCommand(name, tag, draft.replace);
  const blocked = !ok || !tag || (exists && !draft.replace);
  return (
    <Card>
      <CardHeader>
        <CardTitle>{draft.replace ? "Update snapshot" : "New snapshot"}</CardTitle>
        <CardDescription>
          {draft.replace
            ? "Same Worker, same link: whoever has the URL sees the chosen version from now on. The audit runs again, an older version is refused without --force, and earlier versions stay on Cloudflare."
            : "Run the command in the repo on the Mac: it audits the public build, then deploys snapshot-<date>-<name>."}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-col gap-2 sm:flex-row">
          {options.length ? (
            <select
              aria-label="Knowledge version"
              className="h-9 w-full min-w-0 rounded-md border bg-transparent px-2 text-sm sm:w-auto sm:max-w-[28rem] sm:flex-1"
              value={version}
              onChange={(e) => setPicked(e.target.value)}
            >
              {options.map((o) => (
                <option key={o.tag} value={o.tag}>
                  {o.tag} · {o.date}{o.subject ? ` · ${o.subject}` : ""}
                </option>
              ))}
            </select>
          ) : (
            <Input aria-label="Knowledge version" placeholder="kb-x.y.z" value={free} onChange={(e) => setFree(e.target.value)} spellCheck={false} />
          )}
          <Input
            aria-label="Snapshot name"
            className="sm:flex-1"
            placeholder="name (e.g. cohen)"
            maxLength={40}
            value={draft.name}
            pattern={NAME_RE.source}
            onChange={(e) => onDraft({ ...draft, name: e.target.value })}
            autoComplete="off"
            spellCheck={false}
          />
        </div>
        {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={draft.replace} onChange={(e) => onDraft({ ...draft, replace: e.target.checked })} />
          update in place (keep the link)
        </label>
        <div className="flex flex-wrap items-center gap-2">
          <code className="min-w-0 flex-1 break-all rounded bg-muted p-2 font-mono text-xs" data-testid="snapshot-command">{cmd}</code>
          {blocked ? <Button variant="secondary" size="sm" disabled>Copy</Button> : <CopyButton text={cmd} />}
        </div>
      </CardContent>
    </Card>
  );
}

/** History and rollback exist only in the CLI (the Worker API has no endpoint for them): pick a snapshot, copy the command. */
function CliHelp({ snapshots }: { snapshots: readonly Snapshot[] }) {
  const [worker, setWorker] = useState("");
  const s = snapshots.find((x) => x.worker === worker) ?? snapshots[0];
  if (!s) return null;
  const rows: [string, string][] = [
    ["History of every version served at this link", historyCommand(s.name)],
    ["Roll back to the previous version", rollbackCommand(s.worker)],
  ];
  return (
    <details className="rounded-lg border p-3 text-sm">
      <summary className="cursor-pointer font-medium">History and rollback (CLI)</summary>
      <div className="mt-3 flex flex-col gap-2">
        <select aria-label="Snapshot for the CLI commands" className="h-9 w-full rounded-md border bg-transparent px-2 text-sm sm:w-auto sm:self-start" value={s.worker} onChange={(e) => setWorker(e.target.value)}>
          {snapshots.map((x) => <option key={x.worker} value={x.worker}>{x.name}</option>)}
        </select>
        {rows.map(([label, cmd]) => (
          <div key={cmd} className="flex flex-col gap-1">
            <span className="text-xs text-muted-foreground">{label}</span>
            <div className="flex flex-wrap items-center gap-2">
              <code className="min-w-0 flex-1 break-all rounded bg-muted p-2 font-mono text-xs">{cmd}</code>
              <CopyButton text={cmd} />
            </div>
          </div>
        ))}
      </div>
    </details>
  );
}

export function ShareScreen({ client }: { client?: AdminClient }) {
  const api = useMemo(() => client ?? createAdminClient(), [client]);
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["share", "snapshots"], queryFn: () => api.listSnapshots(), retry: false });
  const prune = useQuery({ queryKey: ["share", "prune"], queryFn: () => api.prunePlan(), retry: false, enabled: list.isSuccess });
  const [draft, setDraft] = useState({ name: "", replace: false });
  const [target, setTarget] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const del = useMutation({
    mutationFn: ({ worker, typed }: { worker: string; typed: string }) => api.deleteSnapshot(worker, typed),
    onSuccess: async (r) => {
      setTarget(null);
      setNotice(`Deleted ${r.deleted}.`);
      await qc.invalidateQueries({ queryKey: ["share"] });
    },
  });
  const known = useMemo(() => new Set((list.data?.snapshots ?? []).map((s) => s.name)), [list.data]);
  const refresh = () => {
    setNotice("");
    void qc.invalidateQueries({ queryKey: ["share"] });
  };

  let body: ReactNode;
  if (list.isPending) body = <Loading label="Loading snapshots" />;
  else if (list.isError) {
    const x = explain(list.error);
    body = x.kind === "setup" ? <Setup message={x.message} /> : <ErrorState title={x.message} onRetry={() => void list.refetch()} />;
  } else {
    const { snapshots, main, notes } = list.data;
    body = (
      <>
        {prune.data && <PruneBanner plan={prune.data} />}
        {snapshots.length === 0 ? (
          <Empty>No snapshots yet.</Empty>
        ) : (
          <div className="relative min-w-0 overflow-x-auto">
            <table className="w-full min-w-max text-left text-sm [&_th]:pb-1.5 [&_th]:pr-4 [&_th]:text-xs [&_th]:font-medium [&_th]:text-muted-foreground">
              <thead>
                <tr><th>Name</th><th>kb version</th><th>Behind main</th><th className="text-right">Views 7d</th><th>Built</th><th>Online</th><th><span className="sr-only">Actions</span></th></tr>
              </thead>
              <tbody>
                {snapshots.map((s) => (
                  <SnapshotRow
                    key={s.worker}
                    s={s}
                    onDelete={setTarget}
                    onUpdate={(x) => setDraft({ name: x.name, replace: true })}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
        <CliHelp snapshots={snapshots} />
        {notes.length > 0 && (
          <ul className="list-disc pl-5 text-xs text-muted-foreground">{notes.map((n) => <li key={n}>{n}</li>)}</ul>
        )}
        <p className="text-xs text-muted-foreground" data-testid="main-version">
          {main.kb_version ? `main is kb-${main.kb_version}` : "main version unknown"}
        </p>
      </>
    );
  }

  return (
    <div className="mx-auto flex w-full min-w-0 max-w-5xl flex-col gap-4 px-4 py-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-xl font-semibold">Snapshots</h1>
        <span className="flex-1" />
        <Button variant="secondary" size="sm" onClick={refresh}><RefreshCw /> Refresh</Button>
      </div>
      <p className="text-sm text-muted-foreground">
        Public, forwardable copies of a knowledge version. Anyone with the link can open one. Deleting is done here; creating,
        updating, pruning and rolling back run from the CLI on the Mac (copy the command).
      </p>
      {notice && <p role="status" className="text-sm text-ok">{notice}</p>}
      {body}
      <NewSnapshot known={known} draft={draft} onDraft={setDraft} />
      <DeleteDialog
        key={target ?? "none"}
        worker={target}
        onClose={() => { setTarget(null); del.reset(); }}
        onConfirm={(worker, typed) => del.mutate({ worker, typed })}
        pending={del.isPending}
        error={del.isError ? explain(del.error).message : null}
      />
    </div>
  );
}
