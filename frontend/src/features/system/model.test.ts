import { askAbout } from "@/features/graph/tools/chatDockStore";
import { needsYou, runReason, tiles, timeline, type HealthLike, type LifecycleLike, type OpsLike } from "./model";

const lc: LifecycleLike = {
  version: "1.0.9",
  github: "https://github.com/o/r",
  working: { lanes: { knowledge: 1, tooling: 0 } },
  timeline: [
    { sha: "aaaaaaaaaaaa", short: "aaaaaaa", date: "2026-10-24T10:00:00Z", subject: "kb(digest): x (kb-1.0.9)", kind: "kb", kb_version: "1.0.9" },
    { sha: "bbbbbbbbbbbb", short: "bbbbbbb", date: "2026-10-24T12:00:00Z", subject: "feat(frontend): y (#93)", kind: "pr-merge", pr: 93 },
  ],
};
const ops: OpsLike = {
  threads: [
    { id: "a", title: "ok thread", status: "", age_hours: 1 },
    { id: "b", title: "stale thread", status: "warn", age_hours: 5, next: "pixi run lanes" },
  ],
  hygiene: { errors: 0, warnings: 2, findings: [{ severity: "warn", kind: "stale-worktree", detail: "d", fix: "pixi run ship -- prune --apply" }] },
  runs: [{ started: "2026-10-24T11:00:00Z", status: "warn", duration: 88.9, warnings: 2, sync: { commits: 1, pushed: true } }],
  nightly: { summary: "ok (last run 2026-10-23T22:11)" },
};
const health: HealthLike = { inbox_count: 4, values: { errors: 0, warnings: 194, queued: 385, partial_books: 2 }, statuses: { warnings: "warn" } };

describe("system model", () => {
  it("builds seven tiles, each from one snapshot, with a placeholder while loading", () => {
    const t = tiles(lc, ops, health);
    expect(t.map((x) => x.id)).toEqual(["version", "work", "hygiene", "lint", "backlog", "nightly", "merges"]);
    expect(t.find((x) => x.id === "merges")).toMatchObject({ value: "unknown", tone: "warn" });
    expect(t.find((x) => x.id === "version")).toMatchObject({ value: "kb-1.0.9", tone: "warn", tab: "history" });
    expect(t.find((x) => x.id === "work")).toMatchObject({ value: "2", hint: "1 need attention", tone: "warn" });
    expect(t.find((x) => x.id === "hygiene")).toMatchObject({ value: "0 / 2", tone: "warn" });
    expect(t.find((x) => x.id === "lint")).toMatchObject({ value: "0 / 194", tone: "warn", tab: "health" });
    expect(t.find((x) => x.id === "backlog")).toMatchObject({ value: "385", tab: "pipeline" });
    expect(t.find((x) => x.id === "nightly")).toMatchObject({ value: "warn", tone: "warn" });
    expect(tiles().every((x) => x.value === "…" && x.tone === "")).toBe(true);
  });

  it("merges kb steps, merges and nightly runs newest first", () => {
    const ev = timeline(lc, ops);
    expect(ev.map((e) => e.kind)).toEqual(["tooling", "nightly", "knowledge"]);
    expect(ev[0]).toMatchObject({ title: "feat(frontend): y (#93)", href: "https://github.com/o/r/commit/bbbbbbbbbbbb" });
    expect(ev[1]?.sub).toBe("89 s · 1 commit pushed · 2 warnings");
    expect(ev[2]?.sub).toBe("aaaaaaa · kb-1.0.9");
  });

  it("drafts a chat question about a selection, as wikilinks, capped", () => {
    expect(askAbout([{ id: "a" }, { id: "b" }])).toBe("About [[a]], [[b]]: ");
    expect(askAbout(Array.from({ length: 14 }, (_, i) => ({ id: `p${i}` })), 2)).toBe("About [[p0]], [[p1]] (and 12 more): ");
  });

  it("the Nightly tile follows the latest run, red with its reason when it failed", () => {
    const failed: OpsLike = {
      ...ops,
      nightly: { summary: "ok (last run 2026-10-24T22:00)" },
      runs: [
        { started: "2026-10-23T19:00:00Z", status: "ok" },
        {
          started: "2026-10-24T19:00:26Z",
          status: "error",
          errors: 1,
          deploy: { state: "failed" },
          steps: [{ name: "hygiene", status: "error" }, { name: "report", status: "error" }, { name: "notify", status: "ok" }],
        },
      ],
    };
    const t = tiles(lc, failed, health).find((x) => x.id === "nightly");
    expect(t).toMatchObject({ value: "error", tone: "bad" });
    expect(t?.hint).toMatch(/^site deploy failed · /);
    expect(runReason({ started: "", steps: [{ name: "hygiene", status: "error" }] })).toBe("hygiene failed");
    expect(runReason({ started: "", sync: { failed: true }, deploy: { state: "failed" } })).toBe("sync failed");
    const fine = tiles(lc, { ...ops, runs: [{ started: "2026-10-24T19:00:00Z", status: "ok" }] }, health).find((x) => x.id === "nightly");
    expect(fine).toMatchObject({ value: "ok", tone: "ok" });
    expect(tiles(lc, { ...ops, runs: [], nightly: {} }, health).find((x) => x.id === "nightly")).toMatchObject({ value: "not installed", tone: "warn" });
  });

  it("the Merges tile reads the live queue: idle ok, waiters warn, stale or dead holder bad", () => {
    const m = (queue: OpsLike["queue"]) => tiles(lc, { ...ops, queue }, health).find((x) => x.id === "merges");
    expect(m({ holder: null, waiters: [], stale_after: 1200 })).toMatchObject({ value: "idle", tone: "ok" });
    expect(m({ holder: { pr: 7, held: 30, alive: true }, waiters: [], stale_after: 1200 })).toMatchObject({ value: "#7 merging", hint: "merging 30s", tone: "ok" });
    expect(m({ holder: { pr: 7, held: 30, alive: true }, waiters: [{ pr: 8 }, { branch: "infra/x" }], stale_after: 1200 })).toMatchObject({
      tone: "warn",
      hint: "merging 30s · 2 waiting (#8, infra/x)",
    });
    expect(m({ holder: { pr: 7, held: 1500, alive: true }, waiters: [], stale_after: 1200 })).toMatchObject({ value: "#7 stuck", hint: "stale, held 25m", tone: "bad" });
    expect(m({ holder: { pr: 7, pid: 42, held: 5, alive: false }, waiters: [{ pr: 8 }], stale_after: 1200 })).toMatchObject({ tone: "bad", hint: "pid 42 dead · 1 waiting (#8)" });
    expect(tiles(lc, undefined, health).find((x) => x.id === "merges")).toMatchObject({ value: "…", tone: "" });
  });

  it("lists threads that need attention first", () => {
    const n = needsYou(ops);
    expect(n.threads.map((t) => t.id)).toEqual(["b", "a"]);
    expect(n.findings).toHaveLength(1);
  });
});
