import { Link } from "@tanstack/react-router";
import { CopyButton } from "@/components/CopyButton";
import { ErrorState, Loading } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useFlag } from "@/flags/useFlag";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useApiQuery } from "@/lib/useApiQuery";
import type { KbInfo, KbRow, KbType } from "@/api/types";

const LAYER_LABEL = { concept: "Concepts", collection: "Collections", source: "Sources" } as const;

function GitCell({ git }: { git: KbRow["git"] }) {
  if (!git.repo) return <span className="text-xs text-muted-foreground">plain folder</span>;
  return (
    <span className="flex flex-wrap items-center gap-1 text-xs">
      <Badge variant="outline">{git.branch || "detached"}</Badge>
      {git.last_tag && <span className="tabular-nums text-muted-foreground">{git.last_tag}</span>}
      <span className={git.dirty ? "text-warn" : "text-ok"}>{git.dirty ? `${git.dirty} uncommitted` : "clean"}</span>
    </span>
  );
}

function TypesTable({ types }: { types: KbType[] }) {
  const layers = (["concept", "collection", "source"] as const).map((l) => ({ l, types: types.filter((t) => t.layer === l) }));
  return (
    <div className="grid gap-3 md:grid-cols-3" data-tour="kb-types">
      {layers.map(({ l, types: ts }) => (
        <div key={l} className="rounded-lg border p-2">
          <p className="mb-1 text-xs font-medium text-muted-foreground">{LAYER_LABEL[l]}</p>
          <ul className="flex flex-col gap-0.5 text-sm">
            {ts.map((t) => (
              <li key={t.id} className="flex items-center gap-2">
                <span aria-hidden className="size-2.5 shrink-0 rounded-full" style={{ background: t.color }} />
                <span>{t.label}</span>
                <code className="text-xs text-muted-foreground">{t.prefix ? `${t.prefix}*` : "bare"}</code>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

function Active({ kb }: { kb: KbInfo }) {
  const digestFromKb = kb.digest.some((d) => d.origin === "kb");
  return (
    <Card data-tour="kb-active">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {kb.name} {kb.id && <Badge variant="outline">{kb.id}</Badge>}
        </CardTitle>
        <CardDescription>
          The knowledge base this app was launched with. Schema {kb.schema_version}
          {kb.config && <> · <code className="text-xs">{kb.config}</code></>}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 text-sm">
        <dl className="grid gap-x-4 gap-y-1 sm:grid-cols-[auto_1fr]">
          <dt className="text-muted-foreground">Folder</dt>
          <dd className="flex min-w-0 items-center gap-2"><code className="truncate text-xs">{kb.root}</code><CopyButton text={kb.root} /></dd>
          <dt className="text-muted-foreground">Git</dt>
          <dd data-tour="kb-git"><GitCell git={kb.git} /></dd>
          <dt className="text-muted-foreground">Think</dt>
          <dd className="flex min-w-0 flex-wrap items-center gap-2" data-tour="kb-think">
            <code className="truncate text-xs">{kb.think_root}</code>
            <span className="text-xs text-muted-foreground">shared by every knowledge base</span>
            <GitCell git={kb.think_git} />
          </dd>
          <dt className="text-muted-foreground">Digest instructions</dt>
          <dd data-tour="kb-digest">
            {kb.digest.map((d) => (
              <span key={d.part} className="mr-3 inline-flex items-center gap-1">
                <code className="text-xs">{d.part}</code>
                <Badge variant="outline">{d.origin === "kb" ? "this kb" : "explorer default"}</Badge>
              </span>
            ))}
            {!digestFromKb && <span className="text-xs text-muted-foreground">add digest/focus.md and digest/types.md to the kb to override</span>}
          </dd>
          <dt className="text-muted-foreground">Meta</dt>
          <dd data-tour="kb-meta">
            flags from <Badge variant="outline">{kb.flags_registry === "kb" ? "this kb" : "explorer meta-defaults"}</Badge>
            {kb.meta_overrides.length > 0 && <span className="ml-2 text-xs text-muted-foreground">overrides: {kb.meta_overrides.join(", ")}</span>}
          </dd>
          {kb.areas.length > 0 && (
            <>
              <dt className="text-muted-foreground">Areas</dt>
              <dd className="flex flex-wrap gap-1">{kb.areas.map((a) => <Badge key={a} variant="outline">{a}</Badge>)}</dd>
            </>
          )}
          {kb.source_fields.length > 0 && (
            <>
              <dt className="text-muted-foreground">Source fields</dt>
              <dd className="text-xs">{kb.source_fields.join(", ")}</dd>
            </>
          )}
        </dl>
        <div>
          <p className="mb-1 text-xs font-medium text-muted-foreground">Types (kb.toml [types])</p>
          <TypesTable types={kb.types} />
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * System → Knowledge bases: the one this app serves (folder, git, think, what it overrides, its types) and every
 * knowledge base the explorer can load. Switching is a relaunch: ROOT is resolved when the server starts.
 */
export function KnowledgeBasesView() {
  const kb = useApiQuery(["kb"], (d) => d.getKb(), { staleTime: 60_000 });
  const list = useApiQuery(["kb-list"], (d) => d.listKbs(), { staleTime: 60_000 });
  const kbView = useFlag("kb-view");
  if (kb.error) return <ErrorState title="Could not read the knowledge base" error={kb.error} onRetry={() => void kb.refetch()} />;
  if (!kb.data) return <Loading label="Reading kb.toml…" />;
  return (
    <div className="flex flex-col gap-4">
      <Active kb={kb.data} />
      <Card data-tour="kb-list">
        <CardHeader>
          <CardTitle>Available knowledge bases</CardTitle>
          <CardDescription>
            Every folder with a <code className="text-xs">kb.toml</code> in <code className="text-xs">{list.data?.bases_dir ?? kb.data.bases_dir}</code>
            {" "}(the folder name is the id), or any folder passed as <code className="text-xs">--kb &lt;path&gt;</code>. To switch: <code className="text-xs">{kb.data.relaunch}</code>
          </CardDescription>
        </CardHeader>
        <CardContent>
          {list.error && <ErrorState title="Could not list knowledge bases" error={list.error} onRetry={() => void list.refetch()} />}
          {list.data && (
            <table className="w-full text-left text-sm" data-testid="kb-table">
              <thead className="text-xs text-muted-foreground">
                <tr className="border-b">
                  <th className="py-2 pr-3 font-medium">Id</th>
                  <th className="py-2 pr-3 font-medium">Name</th>
                  <th className="py-2 pr-3 font-medium">Schema</th>
                  <th className="py-2 pr-3 font-medium">Git</th>
                  <th className="py-2 pr-3 font-medium">Folder</th>
                  {kbView && <th className="py-2 pr-3 font-medium"><span className="sr-only">View</span></th>}
                </tr>
              </thead>
              <tbody>
                {list.data.kbs.map((r) => (
                  <tr key={r.id} className="border-b last:border-0" data-active={r.active || undefined}>
                    <td className="py-2 pr-3">
                      <span className="flex items-center gap-2">
                        <code>{r.id}</code>
                        {r.active && <Badge>active</Badge>}
                      </span>
                    </td>
                    <td className="py-2 pr-3">{r.error ? <span className="text-bad">{r.error}</span> : r.name}</td>
                    <td className="py-2 pr-3 tabular-nums">{r.schema_version}</td>
                    <td className="py-2 pr-3"><GitCell git={r.git} /></td>
                    <td className="py-2 pr-3"><code className="text-xs">{r.root}</code></td>
                    {kbView && (
                      <td className="py-2 pr-3">
                        {!r.error && (
                          <Button variant="outline" size="sm" asChild data-tour={r.active ? undefined : "kb-view-button"}>
                            <Link to={"/graph" as "/"} search={(r.active ? {} : { kbs: r.id }) as never} title={r.active ? "Open the graph" : "Open its graph, view only"}>
                              View
                            </Link>
                          </Button>
                        )}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
