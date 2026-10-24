import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  fmtAge, fmtSize, groupByMonth, groupLabel, type Group, type Unit,
} from "./items";
import { Dot, formatColor, StatusPill } from "./parts";

const PAGE = 200;
const CARD_CAP = 30;

export interface ViewProps {
  groups: [string, Unit[]][];
  group: Group;
  titles: Record<string, string>;
  activeKey?: string;
  onOpen: (key: string) => void;
  onFilter: (patch: { format?: string; collection?: string }) => void;
}

function UnitName({ u, onOpen, active }: { u: Unit; onOpen: (k: string) => void; active: boolean }) {
  const extra = u.isThread ? `${u.files.length} files` : u.companions.length ? `+${u.companions.length}` : "";
  return (
    <>
      <button
        type="button"
        className={`max-w-full break-all text-left font-medium hover:underline focus-visible:underline ${active ? "text-primary" : ""}`}
        onClick={() => onOpen(u.key)}
        aria-label={`Preview ${u.name}`}
      >
        {u.name}
      </button>
      {extra && <span className="ml-1 whitespace-nowrap text-xs text-muted-foreground">{extra}</span>}
      {u.failure && <div className="text-xs text-bad" title={u.failure}>{u.failure}</div>}
    </>
  );
}

function GroupHeader({ id, label, count, closed, toggle }: { id: string; label: string; count: number; closed: boolean; toggle: (id: string) => void }) {
  return (
    <button
      type="button"
      className="flex w-full items-center gap-2 border-b bg-secondary/50 px-3 py-1.5 text-left text-sm font-medium"
      aria-expanded={!closed}
      onClick={() => toggle(id)}
    >
      <span aria-hidden>{closed ? "▸" : "▾"}</span>
      {label}
      <span className="text-xs font-normal text-muted-foreground">{count}</span>
    </button>
  );
}

function useCollapse() {
  const [closed, setClosed] = useState<ReadonlySet<string>>(new Set());
  const toggle = (id: string) =>
    setClosed((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  return { closed, toggle };
}

type SortKey = "name" | "format" | "status" | "size" | "age";
const SORTERS: Record<SortKey, (a: Unit, b: Unit) => number> = {
  name: (a, b) => a.name.localeCompare(b.name),
  format: (a, b) => a.format.localeCompare(b.format),
  status: () => 0,
  size: (a, b) => a.sizeKb - b.sizeKb,
  age: (a, b) => (a.ageDays ?? Infinity) - (b.ageDays ?? Infinity),
};

export function ListView({ groups, group, titles, activeKey, onOpen, onFilter }: ViewProps) {
  const { closed, toggle } = useCollapse();
  const [shown, setShown] = useState(PAGE);
  const [sort, setSort] = useState<{ key: SortKey; asc: boolean }>({ key: "status", asc: true });
  const sortRows = (list: Unit[]) => {
    if (sort.key === "status") return list;
    const cmp = SORTERS[sort.key];
    return [...list].sort((a, b) => (sort.asc ? 1 : -1) * cmp(a, b));
  };
  const total = groups.reduce((n, [, m]) => n + m.length, 0);
  let budget = shown;
  const head = (key: SortKey, label: string, cls = "") => (
    <th scope="col" className={`px-3 py-2 font-medium ${cls}`} aria-sort={sort.key === key ? (sort.asc ? "ascending" : "descending") : "none"}>
      <button type="button" className="font-medium hover:underline" onClick={() => setSort((s) => ({ key, asc: s.key === key ? !s.asc : true }))}>
        {label}{sort.key === key ? (sort.asc ? " ↑" : " ↓") : ""}
      </button>
    </th>
  );
  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full min-w-[44rem] text-sm">
        <thead className="border-b text-left text-xs text-muted-foreground">
          <tr>
            {head("name", "Name")}
            {head("format", "Format")}
            <th scope="col" className="px-3 py-2 font-medium">Collection</th>
            {head("status", "Status")}
            <th scope="col" className="px-3 py-2 font-medium">Wiki note</th>
            {head("size", "Size", "text-right")}
            {head("age", "Modified", "text-right")}
          </tr>
        </thead>
        {groups.map(([k, members]) => {
          const id = `${group}|${k}`;
          const isClosed = group !== "none" && closed.has(id);
          const rows = isClosed ? [] : sortRows(members).slice(0, Math.max(budget, 0));
          budget -= rows.length;
          return (
            <tbody key={id}>
              {group !== "none" && (
                <tr>
                  <td colSpan={7} className="p-0">
                    <GroupHeader id={id} label={groupLabel(k, group, titles)} count={members.length} closed={isClosed} toggle={toggle} />
                  </td>
                </tr>
              )}
              {rows.map((u) => (
                <tr key={u.key} className={`border-b last:border-0 ${u.key === activeKey ? "bg-accent-soft" : ""}`}>
                  <td className="max-w-[22rem] px-3 py-1.5"><UnitName u={u} onOpen={onOpen} active={u.key === activeKey} /></td>
                  <td className="px-3 py-1.5">
                    <button type="button" className="inline-flex items-center gap-1.5 text-xs hover:underline" onClick={() => onFilter({ format: u.format })} title="Filter by this format">
                      <Dot color={formatColor(u.format)} />{u.format}
                    </button>
                  </td>
                  <td className="max-w-[14rem] px-3 py-1.5 text-xs">
                    {u.collections.length ? (
                      <button type="button" className="truncate text-left hover:underline" onClick={() => onFilter({ collection: u.collections[0] })} title={`${u.collections[0]}: filter`}>
                        {titles[u.collections[0]!] ?? u.collections[0]}{u.collections.length > 1 ? ` +${u.collections.length - 1}` : ""}
                      </button>
                    ) : <span className="text-muted-foreground">-</span>}
                  </td>
                  <td className="px-3 py-1.5"><StatusPill status={u.status} depth={u.depth} /></td>
                  <td className="max-w-[12rem] truncate px-3 py-1.5 text-xs text-muted-foreground" title={u.slug}>{u.slug || "-"}</td>
                  <td className="whitespace-nowrap px-3 py-1.5 text-right text-xs tabular-nums">{fmtSize(u.sizeKb)}</td>
                  <td className="whitespace-nowrap px-3 py-1.5 text-right text-xs tabular-nums">{fmtAge(u.ageDays)}</td>
                </tr>
              ))}
            </tbody>
          );
        })}
      </table>
      {total > shown && (
        <div className="border-t p-2 text-center">
          <Button variant="secondary" size="sm" onClick={() => setShown((n) => n + PAGE)}>
            Show {Math.min(PAGE, total - shown)} more of {total - shown}
          </Button>
        </div>
      )}
    </div>
  );
}

function Card({ u, onOpen, active }: { u: Unit; onOpen: (k: string) => void; active: boolean }) {
  return (
    <div className={`rounded-md border bg-card p-2 text-sm ${active ? "border-primary" : ""}`}>
      <UnitName u={u} onOpen={onOpen} active={active} />
      <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
        <Dot color={formatColor(u.format)} />{u.format}
        <span className="ml-auto whitespace-nowrap">{fmtSize(u.sizeKb)} · {fmtAge(u.ageDays)}</span>
      </div>
    </div>
  );
}

export function BoardView({ groups, group, titles, activeKey, onOpen }: ViewProps) {
  const { closed, toggle } = useCollapse();
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  return (
    <div className="flex items-start gap-3 overflow-x-auto pb-2">
      {groups.map(([k, members]) => {
        const id = `${group}|${k}`;
        const isClosed = closed.has(id);
        const cap = expanded.has(id) ? members.length : CARD_CAP;
        const label = groupLabel(k, group === "none" ? "status" : group, titles);
        return (
          <section key={id} aria-label={label} className={`shrink-0 rounded-lg border bg-secondary/30 ${isClosed ? "w-40" : "w-64"}`}>
            <GroupHeader id={id} label={label} count={members.length} closed={isClosed} toggle={toggle} />
            {!isClosed && (
              <div className="flex max-h-[70vh] flex-col gap-2 overflow-y-auto p-2">
                {members.slice(0, cap).map((u) => <Card key={u.key} u={u} onOpen={onOpen} active={u.key === activeKey} />)}
                {members.length > cap && (
                  <Button variant="secondary" size="sm" onClick={() => setExpanded((s) => new Set(s).add(id))}>
                    +{members.length - cap} more
                  </Button>
                )}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}

const monthTitle = (m: string) =>
  m === "unknown" ? "Unknown date" : new Date(`${m}-01T00:00:00`).toLocaleDateString(undefined, { month: "long", year: "numeric" });

export function TimelineView({ units, activeKey, onOpen }: { units: Unit[]; activeKey?: string; onOpen: (k: string) => void }) {
  const { closed, toggle } = useCollapse();
  const [shown, setShown] = useState(PAGE);
  let budget = shown;
  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-muted-foreground">Newest first, by the last operation on each item (cataloged, or its wiki note committed). Items nothing has touched have no date.</p>
      {groupByMonth(units).map(([m, members]) => {
        const id = `month|${m}`;
        const isClosed = closed.has(id);
        const rows = isClosed ? [] : members.slice(0, Math.max(budget, 0));
        budget -= rows.length;
        return (
          <section key={m} className="overflow-hidden rounded-lg border">
            <GroupHeader id={id} label={monthTitle(m)} count={members.length} closed={isClosed} toggle={toggle} />
            <ul>
              {rows.map((u) => (
                <li key={u.key} className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 border-b px-3 py-1.5 text-sm last:border-0">
                  <span className="w-28 shrink-0 text-xs tabular-nums text-muted-foreground" title={u.lastOpAt}>{u.lastOpAt.slice(5, 16).replace("T", " ") || "-"}</span>
                  <span className="w-16 shrink-0 text-xs text-muted-foreground">{u.lastOp || "-"}</span>
                  <span className="min-w-0 flex-1"><UnitName u={u} onOpen={onOpen} active={u.key === activeKey} /></span>
                  <StatusPill status={u.status} depth={u.depth} />
                </li>
              ))}
            </ul>
          </section>
        );
      })}
      {units.length > shown && (
        <Button variant="secondary" size="sm" className="self-center" onClick={() => setShown((n) => n + PAGE)}>
          Show more
        </Button>
      )}
    </div>
  );
}
