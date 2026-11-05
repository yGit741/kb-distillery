import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Lock } from "lucide-react";
import { useState } from "react";
import { ErrorState } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { FLAG_ENV, FLAG_NAMES, FLAGS, flag, setFlagOverrides, type FlagEnv, type FlagName } from "@/flags";
import { getOwnerToken, readFlags, setOwnerToken, writeFlag, type FlagsRead } from "@/flags/api";
import { cn } from "@/lib/utils";
import { flagRows, type FlagRow } from "./flagsModel";

const ENVS: FlagEnv[] = ["local", "private", "public"];
const TONE_TEXT = { ok: "text-ok", warn: "text-warn", bad: "text-bad", "": "" } as const;

function Expiry({ row }: { row: FlagRow }) {
  const d = row.expiresInDays;
  const note = d === null ? "" : d < 0 ? `expired ${-d}d ago` : `in ${d}d`;
  return (
    <span data-testid={`flag-${row.name}-expires`} data-tone={row.expiryTone} className={cn("tabular-nums", TONE_TEXT[row.expiryTone])}>
      {row.expires}
      {note && <span className="block text-xs text-muted-foreground">{note}</span>}
    </span>
  );
}

function Toggle({ row, env, busy, onToggle }: { row: FlagRow; env: FlagEnv; busy: boolean; onToggle: () => void }) {
  if (row.kind === "build")
    return (
      <span className="flex items-center gap-1 text-xs text-muted-foreground" title="Build flag: change meta/flags.toml and redeploy">
        <Lock aria-label="build flag" className="size-3.5 shrink-0" /> change meta/flags.toml and redeploy
      </span>
    );
  if (env === "public") return <span className="text-xs text-muted-foreground">read-only</span>;
  return (
    <button
      type="button"
      role="switch"
      aria-checked={row.value}
      aria-label={`Toggle ${row.name}`}
      disabled={busy}
      onClick={onToggle}
      className={cn(
        "relative inline-flex h-6 w-10 shrink-0 items-center rounded-full border transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none disabled:opacity-50",
        row.value ? "bg-primary" : "bg-muted",
      )}
    >
      <span className={cn("inline-block size-5 rounded-full bg-background shadow transition-transform", row.value ? "translate-x-4" : "translate-x-0.5")} />
    </button>
  );
}

/**
 * System → Flags: every flag in meta/flags.toml with owner, age, expiry, per-env values and the effective
 * value here. Runtime flags toggle (owner only: local asks for the keychain token once per page session and
 * keeps it in memory; the private site uses the owner's sign-in). Build flags are locked; public is read-only.
 */
export function FlagsView({ env = FLAG_ENV }: { env?: FlagEnv }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["flags"], queryFn: () => readFlags(), enabled: env !== "public", retry: false });
  const [busy, setBusy] = useState<FlagName | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  // Before/without a fresh GET, fall back to the overrides the app already installed (loadFlagOverrides).
  const installed = Object.fromEntries(FLAG_NAMES.filter((n) => FLAGS[n].kind === "runtime" && env === FLAG_ENV).map((n) => [n, flag(n)]));
  const rows = flagRows(env, q.data?.overrides ?? installed);

  async function toggle(row: FlagRow) {
    setMessage(null);
    if (env === "local" && !getOwnerToken()) {
      const t = window.prompt("Owner token (macOS keychain item kb-flags-owner). Kept in memory for this page only.");
      if (!t?.trim()) return;
      setOwnerToken(t.trim());
    }
    setBusy(row.name);
    const next = !row.value;
    // Flipping back to the registry value clears the override instead of pinning it.
    const res = await writeFlag(row.name, next === row.registryValue ? null : next);
    setBusy(null);
    if (!res.ok) return setMessage(res.message);
    qc.setQueryData<FlagsRead>(["flags"], { overrides: res.overrides, registry: q.data?.registry });
    setFlagOverrides(res.overrides);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Flags</CardTitle>
        <CardDescription>
          <span data-testid="flags-count">{rows.length}</span> flags from{" "}
          <span data-testid="flags-registry">{q.data?.registry === "kb" ? "this knowledge base's meta/flags.toml" : "the explorer's kits/base/defaults/flags.toml"}</span> · this build: {env}
          {env === "public" && " · read-only"}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {message && (
          <p role="alert" className="rounded-md border px-3 py-2 text-sm text-bad">
            {message}
          </p>
        )}
        {q.error && <ErrorState title="Could not load flag overrides (showing registry values)" error={q.error} onRetry={() => void q.refetch()} />}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm" data-testid="flags-table">
            <thead className="text-xs text-muted-foreground">
              <tr className="border-b">
                <th className="py-2 pr-3 font-medium">Flag</th>
                <th className="py-2 pr-3 font-medium">Kind</th>
                <th className="py-2 pr-3 font-medium">Owner</th>
                <th className="py-2 pr-3 font-medium">Created</th>
                <th className="py-2 pr-3 font-medium">Age</th>
                <th className="py-2 pr-3 font-medium">Expires</th>
                {ENVS.map((e) => (
                  <th key={e} className="py-2 pr-3 font-medium">
                    {e}
                  </th>
                ))}
                <th className="py-2 pr-3 font-medium">Effective</th>
                <th className="py-2 font-medium">Change</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.name} data-testid={`flag-${r.name}`} className="border-b align-top last:border-b-0">
                  <td className="py-2 pr-3">
                    <code className="text-xs">{r.name}</code>
                    <p className="max-w-xs text-xs text-muted-foreground">{r.description}</p>
                  </td>
                  <td className="py-2 pr-3">
                    <Badge variant="outline">{r.kind}</Badge>
                  </td>
                  <td className="py-2 pr-3">{r.owner}</td>
                  <td className="py-2 pr-3 tabular-nums">{r.created}</td>
                  <td className="py-2 pr-3 tabular-nums">{r.ageDays === null ? "?" : `${r.ageDays}d`}</td>
                  <td className="py-2 pr-3">
                    <Expiry row={r} />
                  </td>
                  {ENVS.map((e) => (
                    <td key={e} className={cn("py-2 pr-3", e === env && "font-semibold")}>
                      {r.envs[e] ? "on" : "off"}
                    </td>
                  ))}
                  <td className="py-2 pr-3" data-testid={`flag-${r.name}-value`}>
                    {r.value ? "on" : "off"}
                    <span className="block text-xs text-muted-foreground">{r.source}</span>
                  </td>
                  <td className="py-2">
                    <Toggle row={r} env={env} busy={busy === r.name} onToggle={() => void toggle(r)} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
