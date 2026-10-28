import { useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useRouterState } from "@tanstack/react-router";
import { ChevronDown, Database, FolderPlus } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useDataSource } from "@/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useFlag } from "@/flags/useFlag";
import { formatKbs, parseKbs } from "@/lib/kbSelection";
import { useApiQuery } from "@/lib/useApiQuery";

/**
 * The knowledge base this app serves, as the header title: its name from kb.toml, its id as a chip. The
 * explorer is the engine; the content is whichever `knowledge-bases/kb-<id>/` it was launched with. A share
 * build (embedded data) has no /api/kb and shows the plain title. With flag kb-view the title is also the
 * menu that picks which knowledge bases the graph shows (other ones view only), and adds a folder from disk.
 */
export function KbBadge() {
  const ds = useDataSource();
  const kbView = useFlag("kb-view") && ds.kind !== "embedded";
  const q = useApiQuery(["kb"], (d) => d.getKb(), { staleTime: Infinity, retry: false });
  // a share build bakes no kb info (getKb is absent there): keep the title its header always had
  const name = q.data?.name ?? "Thesis Knowledge Base";
  const id = q.data?.id ?? null;
  const title = (
    <>
      <Database aria-hidden className="size-4 text-muted-foreground" />
      <span className="truncate">{name}</span>
      {id && <span className="rounded-full border px-1.5 py-px text-[11px] font-normal text-muted-foreground">{id}</span>}
    </>
  );
  if (kbView && q.data) return <KbMenu title={title} active={id} />;
  return (
    <Link
      to={"/system" as never}
      search={{ tab: "kbs" } as never}
      aria-label="Knowledge base"
      data-tour="kb-badge"
      title={q.data ? `${q.data.root}${q.data.git.repo ? ` · git ${q.data.git.branch}` : ""} — System → Knowledge bases` : undefined}
      className="flex shrink-0 items-center gap-1.5 rounded-md px-1 text-sm font-semibold hover:bg-accent"
    >
      {title}
    </Link>
  );
}

/** The header menu: tick the knowledge bases the graph shows (none is allowed), add a folder from anywhere on disk. */
function KbMenu({ title, active }: { title: React.ReactNode; active: string | null }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const loc = useRouterState({ select: (s) => s.location });
  const onGraph = /\/graph\/?$/.test(loc.pathname);
  const raw = onGraph ? (loc.search as Record<string, unknown>).kbs : undefined;
  const picked = parseKbs(typeof raw === "string" ? raw : undefined);
  const list = useApiQuery(["kb-list"], (d) => d.listKbs(), { staleTime: 30_000 });
  const rows = list.data?.kbs ?? [];
  const shown = picked ?? (active ? [active] : []);
  const others = shown.filter((k) => k !== active).length;

  useEffect(() => {
    if (!open) return;
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
    // the menu's order; one just added is not in `rows` yet and goes last
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

  return (
    <div ref={box} className="relative shrink-0">
      <button
        type="button"
        aria-label="Knowledge bases"
        aria-expanded={open}
        aria-haspopup="dialog"
        data-tour="kb-badge"
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 rounded-md px-1 text-sm font-semibold hover:bg-accent"
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
          className="absolute left-0 top-full z-50 mt-1 w-80 rounded-lg border bg-card p-2 text-sm font-normal shadow-[var(--shadow)]"
        >
          <p className="px-1.5 pb-1 text-xs text-muted-foreground">Shown on the graph. Other knowledge bases are view only.</p>
          {list.isPending && <p className="px-1.5 py-1 text-muted-foreground">Loading…</p>}
          {rows.map((r) => (
            <label
              key={r.id}
              title={r.error || r.root}
              className={`flex items-center gap-2 rounded px-1.5 py-1 ${r.error ? "opacity-50" : "cursor-pointer hover:bg-accent"}`}
            >
              <input type="checkbox" disabled={!!r.error} checked={shown.includes(r.id)} onChange={() => toggle(r.id)} />
              <span className="min-w-0 flex-1 truncate">{r.name || r.id}</span>
              <span className="shrink-0 text-xs text-muted-foreground">{r.error ? "can't open" : r.active ? "this app" : "view only"}</span>
            </label>
          ))}
          <AddFolder onAdded={(kb) => show([...shown.filter((k) => k !== kb), kb])} />
          <div className="mt-1 border-t px-1.5 pt-1.5 text-xs">
            <Link to={"/system" as never} search={{ tab: "kbs" } as never} className="text-primary hover:underline" onClick={() => setOpen(false)}>
              Manage in System → Knowledge bases
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}

/** Add a knowledge base folder from anywhere on disk: a kb.toml at this explorer's schema, its own git repo. */
function AddFolder({ onAdded }: { onAdded: (id: string) => void }) {
  const ds = useDataSource();
  const qc = useQueryClient();
  const [path, setPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const add = async () => {
    const want = path.trim();
    if (!want) return;
    setBusy(true);
    setError("");
    try {
      const before = new Set((qc.getQueryData(["kb-list"]) as { kbs: { id: string }[] } | undefined)?.kbs.map((k) => k.id));
      const next = await ds.registerKb(want);
      qc.setQueryData(["kb-list"], next);
      const added = next.kbs.find((k) => !before.has(k.id));
      setPath("");
      if (added) onAdded(added.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <form
      className="mt-1 flex flex-col gap-1 border-t px-1.5 pt-2"
      onSubmit={(e) => {
        e.preventDefault();
        void add();
      }}
    >
      <label htmlFor="kb-add-path" className="text-xs text-muted-foreground">Add a folder from another place</label>
      <div className="flex gap-1">
        <Input id="kb-add-path" value={path} onChange={(e) => setPath(e.target.value)} placeholder="~/path/to/kb-folder" className="h-8 text-xs" spellCheck={false} />
        <Button type="submit" size="sm" variant="outline" className="h-8 gap-1" disabled={busy || !path.trim()}>
          <FolderPlus aria-hidden className="size-3.5" /> Add
        </Button>
      </div>
      {error && <p role="alert" className="text-xs text-bad">{error}</p>}
    </form>
  );
}
