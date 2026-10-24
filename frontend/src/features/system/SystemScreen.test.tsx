import { createMemoryHistory } from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "@/app/providers";
import { createAppRouter } from "@/app/router";
import { ApiError, type DataSource } from "@/api";
import { mockDataSource } from "@/test/datasource";

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
});
