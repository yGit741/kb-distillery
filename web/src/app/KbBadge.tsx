import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useRouterState } from "@tanstack/react-router";
import { ChevronDown, Database, Plus } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useDataSource } from "@/api";
import type { KbList } from "@/api/types";
import { AddKnowledgeBase, useImportAdapter, type ImportAdapter } from "@/components/kb-import";
import { KbSearch, KbSizeChip, StarredRows, StarToggle } from "@/components/kbPicker";
import { useFlag } from "@/flags/useFlag";
import { formatKbs, matchesKb, parseKbs } from "@/lib/kbSelection";
import { bySize, kbProblem, type KbSize } from "@/lib/kbSize";
import { useApiQuery } from "@/lib/useApiQuery";

/**
 * The header title is 20px tall; WCAG 2.5.8 wants a 24px target. The padding adds the 2px above and below and
 * the negative margin takes it back, so the row does not move; the hover pill is the ::before, which keeps the
 * old 20px size.
 */
const HEADER_TITLE =
  "relative isolate -my-0.5 flex shrink-0 items-center gap-1.5 px-1 py-0.5 text-sm font-semibold before:absolute before:inset-x-0 before:inset-y-0.5 before:-z-10 before:rounded-md hover:before:bg-accent";

/**
 * The knowledge base this app serves, as the header title: its name from kb.toml, its id as a chip. The
 * engine is code only; the content is whichever `kbs/<id>/` (or `--kb <path>`) it was launched with. A share
 * build (embedded data) has no /api/kb and shows the plain title. With flag kb-view the title is also the
 * menu that picks which knowledge bases the graph shows (other ones view only).
 */
export function KbBadge() {
  const ds = useDataSource();
  const adapter = useImportAdapter();
  const kbView = useFlag("kb-view") && ds.kind !== "embedded";
  const q = useApiQuery(["kb"], (d) => d.getKb(), { staleTime: Infinity, retry: false });
  // a share build bakes no kb info (getKb is absent there): keep the title its header always had
  const name = q.data?.name ?? "Knowledge Base";
  const id = q.data?.id ?? null;
  const title = (
    <>
      <Database aria-hidden className="size-4 text-muted-foreground" />
      <span className="truncate">{name}</span>
      {id && <span className="rounded-full border px-1.5 py-px text-[11px] font-normal text-muted-foreground">{id}</span>}
    </>
  );
  if (kbView && q.data) return <KbMenu title={title} active={id} activeName={name} readOnly={q.data.read_only} />;
  const link = (
    <Link
      to={"/system" as never}
      search={{ tab: "kbs" } as never}
      aria-label="Knowledge base"
      data-tour="kb-badge"
      title={q.data ? `${q.data.root}${q.data.git.repo ? ` · git ${q.data.git.branch}` : ""} — System → Knowledge bases` : undefined}
      className={HEADER_TITLE}
    >
      {title}
    </Link>
  );
  // the private share build: no menu (its data is baked in), but a bundle can still be sent to the site's inbox
  return ds.kind === "embedded" && adapter ? <WithAdd adapter={adapter}>{link}</WithAdd> : link;
}

/** The plain title plus one button that opens the "Add knowledge base" dialog (the site's inbox adapter). */
function WithAdd({ adapter, children }: { adapter: ImportAdapter; children: React.ReactNode }) {
  const [adding, setAdding] = useState(false);
  return (
    <div className="flex shrink-0 items-center gap-0.5">
      {children}
      <button
        type="button"
        aria-label="Add knowledge base"
        title="Add knowledge base"
        onClick={() => setAdding(true)}
        className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-accent-foreground"
      >
        <Plus aria-hidden className="size-4" />
      </button>
      <AddKnowledgeBase adapter={adapter} open={adding} onOpenChange={setAdding} />
    </div>
  );
}

const unhealthy = (s: KbSize | undefined) => !!s && kbProblem(s) !== null;

type MenuRow = { id: string; name: string; root: string; error: string; active: boolean; starred: boolean; listed: boolean };

/**
 * The header menu: tick the knowledge bases the graph shows (none is allowed). A search line filters the rows by name
 * or id (Enter shows the first match alone); starred ones (kept by the server, so every browser sees them) lead the
 * menu; the rest follow largest graph first, each with its size in small print, red when it is too small or unlinked.
 */
function KbMenu({ title, active, activeName, readOnly }: { title: React.ReactNode; active: string | null; activeName: string; readOnly: boolean }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [adding, setAdding] = useState(false);
  const adapter = useImportAdapter();
  const ds = useDataSource();
  const qc = useQueryClient();
  const box = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const loc = useRouterState({ select: (s) => s.location });
  const onGraph = /\/graph\/?$/.test(loc.pathname);
  const raw = onGraph ? (loc.search as Record<string, unknown>).kbs : undefined;
  const picked = parseKbs(typeof raw === "string" ? raw : undefined);
  const list = useApiQuery(["kb-list"], (d) => d.listKbs(), { staleTime: 30_000 });
  const sizes = useApiQuery(["kb-stats"], (d) => d.getKbStats(), { staleTime: 60_000, retry: false });
  const sizeOf = (r: MenuRow) => sizes.data?.kbs[r.id];
  const listed: MenuRow[] = (list.data?.kbs ?? []).map((r) => ({ ...r, listed: true }));
  // an app opened on a folder outside the bases dir (`--kb <path>`) is on the graph too: it gets its row, first
  const rows = bySize(
    active && list.data && !listed.some((r) => r.id === active)
      ? [{ id: active, name: activeName, root: "", error: "", active: true, starred: false, listed: false }, ...listed]
      : listed,
    sizeOf,
  );
  const shown = picked ?? (active ? [active] : []);
  const others = shown.filter((k) => k !== active).length;
  const visible = rows.filter((r) => matchesKb(r, query));
  const starredRows = visible.filter((r) => r.starred);
  const restRows = visible.filter((r) => !r.starred);
  const first = [...starredRows, ...restRows].find((r) => !r.error);

  const star = useMutation({
    mutationFn: (v: { id: string; starred: boolean }) => ds.starKb(v.id, v.starred),
    onMutate: async (v) => {
      await qc.cancelQueries({ queryKey: ["kb-list"] });
      qc.setQueryData<KbList>(["kb-list"], (old) => old && { ...old, kbs: old.kbs.map((r) => (r.id === v.id ? { ...r, starred: v.starred } : r)) });
    },
    onSuccess: (data) => qc.setQueryData(["kb-list"], data),
    onError: () => void qc.invalidateQueries({ queryKey: ["kb-list"] }),
  });

  useEffect(() => {
    if (!open) {
      setQuery("");
      return;
    }
    const away = (e: PointerEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("pointerdown", away);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  const show = (ids: string[]) => {
    // the menu's order
    const rank = (id: string) => (rows.findIndex((r) => r.id === id) + 1 || Infinity);
    const sorted = [...ids].sort((a, b) => rank(a) - rank(b));
    void navigate({
      to: "/graph" as "/",
      search: ((prev: Record<string, unknown>) => {
        const next: Record<string, unknown> = { ...(onGraph ? prev : {}), kbs: formatKbs(sorted, active) };
        if (next.kbs === undefined) delete next.kbs;
        return next;
      }) as never,
    });
  };
  const toggle = (kb: string) => show(shown.includes(kb) ? shown.filter((k) => k !== kb) : [...shown, kb]);
  const only = (kb: string) => {
    setOpen(false);
    show([kb]);
  };

  const row = (r: MenuRow) => (
    <div key={r.id} className={`flex items-center gap-1 rounded pr-1 ${r.error ? "" : "hover:bg-accent"}`}>
      <label title={r.error || r.root} className={`flex min-w-0 flex-1 items-center gap-2 px-1.5 py-1 ${r.error ? "opacity-50" : "cursor-pointer"}`}>
        <input type="checkbox" disabled={!!r.error} checked={shown.includes(r.id)} onChange={() => toggle(r.id)} />
        <span className={`min-w-0 flex-1 truncate ${unhealthy(sizeOf(r)) ? "text-destructive" : ""}`}>{r.name || r.id}</span>
        <KbSizeChip size={sizeOf(r)} />
        <span className="shrink-0 text-xs text-muted-foreground">{r.error ? "can't open" : r.active ? "this app" : "view only"}</span>
      </label>
      {r.listed && !readOnly && <StarToggle name={r.name || r.id} on={r.starred} onToggle={() => star.mutate({ id: r.id, starred: !r.starred })} />}
    </div>
  );

  return (
    <div ref={box} className="relative shrink-0">
      <button
        type="button"
        aria-label="Knowledge bases"
        aria-expanded={open}
        aria-haspopup="dialog"
        data-tour="kb-badge"
        onClick={() => setOpen(!open)}
        className={HEADER_TITLE}
      >
        {title}
        {!shown.length ? (
          <span className="text-xs font-normal text-muted-foreground">none shown</span>
        ) : others ? (
          <span className="text-xs font-normal text-muted-foreground">+{others}</span>
        ) : null}
        <ChevronDown aria-hidden className="size-3.5 text-muted-foreground" />
      </button>
      {open && (
        <div
          role="dialog"
          aria-label="Knowledge bases on the graph"
          data-tour="graph-kbs"
          className="absolute left-0 top-full z-50 mt-1 w-[28rem] max-w-[calc(100vw-1rem)] rounded-lg border bg-card p-2 text-sm font-normal shadow-[var(--shadow)]"
        >
          <p className="px-1.5 pb-1 text-xs text-muted-foreground">Shown on the graph. Other knowledge bases are view only.</p>
          <KbSearch value={query} onChange={setQuery} onEnter={() => query.trim() && first && only(first.id)} autoFocus className="mb-1" />
          {list.isPending && <p className="px-1.5 py-1 text-muted-foreground">Loading…</p>}
          <StarredRows
            starred={starredRows}
            rest={restRows}
            row={row}
            empty={list.data && <p className="px-1.5 py-1 text-muted-foreground">No knowledge base matches “{query.trim()}”.</p>}
          />
          {adapter && (
            <button
              type="button"
              className="mt-1 flex w-full items-center gap-1.5 rounded px-1.5 py-1 text-left text-primary hover:bg-accent"
              onClick={() => { setOpen(false); setAdding(true); }}
            >
              <Plus aria-hidden className="size-3.5" />
              Add knowledge base
            </button>
          )}
          <div className="mt-1 border-t px-1.5 pt-1.5 text-xs">
            <Link to={"/system" as never} search={{ tab: "kbs" } as never} className="text-primary hover:underline" onClick={() => setOpen(false)}>
              Manage in System → Knowledge bases
            </Link>
          </div>
        </div>
      )}
      {adapter && <AddKnowledgeBase adapter={adapter} open={adding} onOpenChange={setAdding} />}
    </div>
  );
}
