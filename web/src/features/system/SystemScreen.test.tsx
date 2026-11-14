import { createMemoryHistory } from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "@/app/providers";
import { createAppRouter } from "@/app/router";
import { ApiError, type DataSource } from "@/api";
import { mockDataSource } from "@/test/datasource";
import { withFlag } from "@/flags/testing";

const lifecycle = {
  version: "1.0.9",
  github: "https://github.com/o/r",
  working: { lanes: { knowledge: 0 } },
  timeline: [{ sha: "aaaaaaaaaaaa", short: "aaaaaaa", date: "2026-10-24T10:00:00Z", subject: "kb(digest): ramsey numbers (kb-1.0.9)", kind: "kb", kb_version: "1.0.9" }],
};
const ops = {
  doc: {},
  threads: [{ id: "b", title: "infra/x is merged — leftover worktree", status: "warn", state: "stale", next: "pixi run ship -- prune --apply" }],
  hygiene: { errors: 0, warnings: 1, findings: [] },
  runs: [],
  nightly: { summary: "ok (last run 2026-10-23T22:11)" },
};
const health = { inbox_count: 0, values: { errors: 0, warnings: 3, queued: 10, broken: 2 }, statuses: { warnings: "warn" }, orphan_slugs: ["lonely-page"] };

const base: Partial<DataSource> = {
  getLifecycle: async () => lifecycle as never,
  getOps: async () => ops as never,
  getHealth: async () => health as never,
  getShareStatus: async () => ({ status: null, chip: null }),
  getGraphNodes: async () => [],
};

function open(path: string, over: Partial<DataSource> = {}) {
  const router = createAppRouter(createMemoryHistory({ initialEntries: [path] }), "");
  render(<App source={mockDataSource({ ...base, ...over })} router={router} />);
  return router;
}

describe("System screen", () => {
  it("shows the version, what needs me and the timeline", async () => {
    open("/system");
    expect((await screen.findAllByText("kb-1.0.9")).length).toBeGreaterThan(0);
    expect(await screen.findByText("infra/x is merged — leftover worktree")).toBeInTheDocument();
    expect(screen.getByText("pixi run ship -- prune --apply")).toBeInTheDocument();
    expect(await screen.findByText("kb(digest): ramsey numbers (kb-1.0.9)")).toBeInTheDocument();
  });

  it("tiles carry stable test ids for the integrator's data checks", async () => {
    open("/system");
    await waitFor(() => expect(screen.getByTestId("tile-lint-value")).toHaveTextContent("0 / 3"));
    expect(screen.getByTestId("tile-version-value")).toHaveTextContent("kb-1.0.9");
    expect(screen.getByTestId("tile-lint")).toHaveAttribute("data-tone", "warn");
    for (const id of ["nightly", "merges", "stale", "hygiene", "backlog", "work"]) expect(screen.getByTestId(`tile-${id}-value`)).toBeInTheDocument();
  });

  it("a tile opens its tab and the tab lives in the URL", async () => {
    const router = open("/system");
    await userEvent.click(await screen.findByRole("button", { name: /^lint/i }));
    await waitFor(() => expect(router.state.location.search).toMatchObject({ tab: "health" }));
    expect(await screen.findByText("Broken links")).toBeInTheDocument();
    expect(screen.getByText("lonely-page")).toBeInTheDocument();
  });

  it("shows an error with retry when open work cannot load", async () => {
    open("/system", { getOps: async () => Promise.reject(new ApiError("boom", 500)) });
    expect(await screen.findByText(/could not load open work/i, {}, { timeout: 4000 })).toBeInTheDocument();
  });
  it("the Flags tab is always there in the local app", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ overrides: {} }), { status: 200 })));
    open("/system?tab=flags");
    expect(await screen.findByRole("tab", { name: "Flags" })).toHaveAttribute("aria-selected", "true");
    try {
      expect(await screen.findByTestId("flags-table")).toBeInTheDocument();
    } finally {
      vi.unstubAllGlobals();
    }
  });
});

describe("System screen, flag ui.data-system-split", () => {
  it("on: three tiles, tabs Overview, Knowledge bases, Dev, and Recent runs instead of the mixed timeline", () => withFlag("ui.data-system-split", true, async () => {
    open("/system");
    const tabs = await screen.findByRole("tablist", { name: "System sections" });
    expect([...tabs.querySelectorAll('[role="tab"]')].map((t) => t.textContent?.replace(/\d+$/, ""))).toEqual(["Overview", "Knowledge bases", "Dev"]);
    expect(["tile-nightly", "tile-deploy", "tile-work"].every((id) => screen.getByTestId(id))).toBe(true);
    expect(screen.queryByTestId("tile-lint")).toBeNull();
    expect(await screen.findByText("Recent runs")).toBeInTheDocument();
    expect(screen.queryByText("Timeline")).toBeNull();
  }));

  it("on: old data tabs land in Ingest, old dev tabs in Dev", () => withFlag("ui.data-system-split", true, async () => {
    const router = open("/system?tab=history");
    await waitFor(() => expect(router.state.location.pathname).toBe("/ingest"));
    expect(router.state.location.search).toMatchObject({ tab: "history" });
  }));

  it("off: the nine-tab System stays", () => withFlag("ui.data-system-split", false, async () => {
    open("/system");
    expect(await screen.findByText("Timeline")).toBeInTheDocument();
    expect(screen.getByTestId("tile-lint")).toBeInTheDocument();
  }));
});

describe("movedTab", () => {
  it("sends data tabs to Ingest with the pipeline's params, dev tabs to Dev, and keeps the rest", async () => {
    const { movedTab } = await import("./SystemScreen");
    expect(movedTab({ tab: "pipeline", status: "partial" })).toEqual({ to: "/ingest", search: { tab: "pipeline", status: "partial" } });
    expect(movedTab({ tab: "variants" })).toEqual({ to: "/system", search: { tab: "dev", dev: "variants" } });
    expect(movedTab({ tab: "kbs" })).toBeUndefined();
    expect(movedTab({})).toBeUndefined();
  });
});

describe("System screen, split without Ingest", () => {
  it("ui.data-system-split on but ui.ingest off: no split, the data tabs stay reachable here", () => withFlag("ui.data-system-split", true, () => withFlag("ui.ingest", false, async () => {
    open("/system?tab=history");
    const tabs = await screen.findByRole("tablist", { name: "System sections" });
    expect([...tabs.querySelectorAll('[role="tab"]')].map((t) => t.textContent)).toContain("History");
  })));
});
