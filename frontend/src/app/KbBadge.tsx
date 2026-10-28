import { Link } from "@tanstack/react-router";
import { Database } from "lucide-react";
import { useApiQuery } from "@/lib/useApiQuery";

/**
 * The knowledge base this app serves, as the header title: its name from kb.toml, its id as a chip. The
 * explorer is the engine; the content is whichever `knowledge-bases/kb-<id>/` it was launched with. A share
 * build (embedded data) has no /api/kb and shows the plain title.
 */
export function KbBadge() {
  const q = useApiQuery(["kb"], (d) => d.getKb(), { staleTime: Infinity, retry: false });
  // a share build bakes no kb info (getKb is absent there): keep the title its header always had
  const name = q.data?.name ?? "Thesis Knowledge Base";
  const id = q.data?.id ?? null;
  return (
    <Link
      to={"/system" as never}
      search={{ tab: "kbs" } as never}
      aria-label="Knowledge base"
      data-tour="kb-badge"
      title={q.data ? `${q.data.root}${q.data.git.repo ? ` · git ${q.data.git.branch}` : ""} — System → Knowledge bases` : undefined}
      className="flex shrink-0 items-center gap-1.5 rounded-md px-1 text-sm font-semibold hover:bg-accent"
    >
      <Database aria-hidden className="size-4 text-muted-foreground" />
      <span className="truncate">{name}</span>
      {id && <span className="rounded-full border px-1.5 py-px text-[11px] font-normal text-muted-foreground">{id}</span>}
    </Link>
  );
}
