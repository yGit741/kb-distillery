import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Download, Loader2 } from "lucide-react";
import { useDataSource } from "@/api";
import type { KbInboxItem, KbInboxPull } from "@/api/types";
import { ResultCard } from "@/components/kb-import";
import { Loading } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useApiQuery } from "@/lib/useApiQuery";

const STATUS = { pending: "outline", imported: "ok", failed: "bad" } as const;
const when = (at: string) => at.slice(0, 16).replace("T", " ");
const what = (i: KbInboxItem) => (i.kind === "git" ? i.git_url ?? "git" : `${i.pages ?? 0} ${i.pages === 1 ? "page" : "pages"}`);

function PullResult({ r }: { r: KbInboxPull }) {
  if (!r.imported.length && !r.failed.length) return <ResultCard tone="pending" title="Nothing to pull">No uploads are waiting.</ResultCard>;
  return (
    <ResultCard tone={r.failed.length ? "pending" : "done"} title={r.imported.length ? `Imported ${r.imported.length}` : "Nothing imported"}>
      {r.imported.length > 0 && <p>{r.imported.map((o) => o.kb_id).join(", ")}</p>}
      {r.failed.map((o) => <p key={o.item} className="break-words text-bad">{o.item}: {o.error}</p>)}
      {r.unreported.length > 0 && <p>The site has not heard back about {r.unreported.length}; they stay pending there.</p>}
    </ResultCard>
  );
}

/**
 * System → Knowledge bases → Inbox: what was uploaded on the deployed site (pending, imported, failed), read through the
 * local server (`distill kb inbox list`), and "Pull now" (`distill kb inbox pull`): every pending upload becomes a new kb here.
 * Without a site, token or bucket it is a one-line hint, not an error.
 */
export function KbInbox() {
  const ds = useDataSource();
  const qc = useQueryClient();
  const q = useApiQuery(["kb-inbox"], (d) => d.getKbInbox(), { staleTime: 30_000, retry: false });
  const pull = useMutation({
    mutationFn: () => ds.pullKbInbox(),
    onSettled: () => void Promise.all([qc.invalidateQueries({ queryKey: ["kb-inbox"] }), qc.invalidateQueries({ queryKey: ["kb-list"] })]),
  });
  const items = q.data?.items ?? [];
  const pending = items.filter((i) => i.status === "pending").length;
  return (
    <Card data-tour="kb-inbox">
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <CardTitle>Inbox</CardTitle>
          {q.data?.configured && !q.data.error && (
            <Button variant="outline" size="sm" disabled={!pending || pull.isPending} onClick={() => pull.mutate()}>
              {pull.isPending ? <Loader2 aria-hidden className="animate-spin" /> : <Download aria-hidden />}
              Pull now
            </Button>
          )}
        </div>
        <CardDescription>Bundles uploaded on the deployed site. Pulling imports each one here as a new knowledge base.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {q.isPending && <Loading label="Reading the inbox…" rows={1} />}
        {q.error && <p role="alert" className="text-sm text-bad break-words">Could not read the inbox: {q.error.message}</p>}
        {q.data && !q.data.configured && (
          <p className="text-sm text-muted-foreground">
            Site uploads are not set up on this Mac.{" "}
            {q.data.guide ? (
              <a className="text-primary hover:underline" href={q.data.guide} target="_blank" rel="noreferrer">How to set them up</a>
            ) : (
              <>See <code className="text-xs">docs/guides/import-a-bundle.md</code>.</>
            )}
          </p>
        )}
        {q.data?.error && <p role="alert" className="text-sm text-bad break-words">{q.data.error}</p>}
        {q.data?.configured && !q.data.error && !items.length && <p className="text-sm text-muted-foreground">No uploads yet.</p>}
        {items.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm" data-testid="inbox-table">
              <thead className="text-xs text-muted-foreground">
                <tr className="border-b">
                  <th className="py-2 pr-3 font-medium">Uploaded</th>
                  <th className="py-2 pr-3 font-medium">Id</th>
                  <th className="py-2 pr-3 font-medium">What</th>
                  <th className="py-2 pr-3 font-medium">By</th>
                  <th className="py-2 pr-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {items.map((i) => (
                  <tr key={i.item} className="border-b align-top last:border-0">
                    <td className="py-2 pr-3 tabular-nums">{when(i.at)}</td>
                    <td className="py-2 pr-3"><code>{i.kb_id || "—"}</code></td>
                    <td className="py-2 pr-3 break-all text-xs">{what(i)}</td>
                    <td className="py-2 pr-3 text-xs">{i.uploader}</td>
                    <td className="py-2 pr-3">
                      <Badge variant={STATUS[i.status as keyof typeof STATUS] ?? "outline"}>{i.status}</Badge>
                      {i.error && <p className="mt-1 break-words text-xs text-bad">{i.error}</p>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {pull.error && <p role="alert" className="text-sm text-bad break-words">{pull.error.message}</p>}
        {pull.data && <PullResult r={pull.data} />}
      </CardContent>
    </Card>
  );
}
