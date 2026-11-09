import { Link } from "@tanstack/react-router";
import type { ProposalSummary } from "@/api";
import { Empty, ErrorState, Loading } from "@/components/states";
import { useApiQuery } from "@/lib/useApiQuery";

const when = (iso: string) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
};

function counts(p: ProposalSummary): string {
  const c = p.counts;
  const parts = [`${c.hunks} ${c.hunks === 1 ? "change" : "changes"}`];
  if (c.accepted) parts.push(`${c.accepted} accepted`);
  if (c.rejected) parts.push(`${c.rejected} rejected`);
  if (c.corrected) parts.push(`${c.corrected} corrected`);
  if (p.checks.errors) parts.push(`${p.checks.errors} ${p.checks.errors === 1 ? "error" : "errors"}`);
  return parts.join(" · ");
}

/** A plain list of proposals, newest first, so each review screen is reachable. */
export function ProposalList() {
  const q = useApiQuery(["proposals"], (ds) => ds.listProposals());
  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-4 px-4 pt-6">
      <header>
        <h1 className="text-xl font-semibold">Proposals</h1>
        <p className="text-sm text-muted-foreground">Changes an agent suggests for your pages. Open one to accept, reject or correct it part by part.</p>
      </header>
      {q.isLoading ? (
        <Loading label="Loading proposals" />
      ) : q.error ? (
        <ErrorState title="Could not load proposals" error={q.error} onRetry={() => void q.refetch()} />
      ) : !q.data?.length ? (
        <Empty>No proposals yet.</Empty>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted-foreground">
              <tr className="border-b">
                <th className="py-2 pr-4 font-medium">Title</th>
                <th className="py-2 pr-4 font-medium">Pages</th>
                <th className="py-2 pr-4 font-medium">Changes</th>
                <th className="py-2 pr-4 font-medium">Status</th>
                <th className="py-2 font-medium">Created</th>
              </tr>
            </thead>
            <tbody>
              {q.data.map((p) => (
                <tr key={p.id} className="border-b last:border-0 hover:bg-accent/40">
                  <td className="py-2 pr-4">
                    <Link to={`/proposals/${encodeURIComponent(p.id)}` as "/"} className="font-medium hover:underline">
                      {p.title}
                    </Link>
                  </td>
                  <td className="py-2 pr-4 text-muted-foreground">{p.pages.join(", ")}</td>
                  <td className="py-2 pr-4 text-muted-foreground">{counts(p)}</td>
                  <td className="py-2 pr-4 text-muted-foreground">{p.status}</td>
                  <td className="whitespace-nowrap py-2 text-muted-foreground">{when(p.created)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
