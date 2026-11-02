import { Link, useNavigate, useRouterState } from "@tanstack/react-router";
import { ChevronDown, Database } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useDataSource } from "@/api";
import { useFlag } from "@/flags/useFlag";
import { formatKbs, parseKbs } from "@/lib/kbSelection";
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
  if (kbView && q.data) return <KbMenu title={title} active={id} />;
  return (
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
}

/** The header menu: tick the knowledge bases the graph shows (none is allowed). */
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
