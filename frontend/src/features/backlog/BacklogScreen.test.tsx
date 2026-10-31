import { createMemoryHistory } from "@tanstack/react-router";
import { render, screen } from "@testing-library/react";
import { App } from "@/app/providers";
import { createAppRouter } from "@/app/router";
import { ApiError } from "@/api";
import type { BacklogItem } from "@/api/types";
import { mockDataSource } from "@/test/datasource";
import { driftChip } from "./index";

const item = (over: Partial<BacklogItem>): BacklogItem => ({
  id: "20261031-x",
  title: "Try a calmer legend",
  kind: "idea",
  area: "graph",
  size: "s",
  status: "inbox",
  created: "2026-10-31",
  source: "",
  plan_status: "no-plan",
  base_sha: "",
  branch: "",
  paths: [],
  why: "less noise",
  drift: { level: "none", commits: 0, missing: [], maybe_done: [] },
  ...over,
});

function setup(items: BacklogItem[] | Error) {
  const ds = mockDataSource({
    listBacklog: async () => {
      if (items instanceof Error) throw items;
      return { items, dir: "/x/.backlog" };
    },
    listPages: async () => ({ generated_at: "", pages: [], links: [], wanted: [], wanted_total: 0 }),
    getShareStatus: async () => ({ status: null, chip: null }),
  });
  const router = createAppRouter(createMemoryHistory({ initialEntries: ["/app/backlog"] }));
  render(<App source={ds} router={router} />);
}

describe("BacklogScreen", () => {
  it("groups cards by status and shows plan status", async () => {
    setup([
      item({ id: "a", title: "Idea card" }),
      item({ id: "b", title: "Plan card", kind: "plan", plan_status: "has-plan", status: "next", drift: { level: "drifted", commits: 3, missing: [], maybe_done: [] } }),
    ]);
    expect(await screen.findByText("Idea card")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Inbox" })).toHaveTextContent("No plan");
    expect(screen.getByRole("region", { name: "Next" })).toHaveTextContent("Has plan");
    expect(screen.getByRole("region", { name: "Next" })).toHaveTextContent("3 commits since");
  });

  it("says so when nothing is parked", async () => {
    setup([]);
    expect(await screen.findByText("Nothing parked yet.")).toBeInTheDocument();
  });

  it("shows an error with retry", async () => {
    setup(new ApiError("backend down", 404));
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load the backlog");
  });
});

describe("driftChip", () => {
  const plan = (drift: BacklogItem["drift"], over: Partial<BacklogItem> = {}) =>
    item({ plan_status: "has-plan", kind: "plan", drift, ...over });

  it("is absent for ideas, closed items and plans without paths", () => {
    expect(driftChip(item({}))).toBeNull();
    expect(driftChip(plan({ level: "closed", commits: 0, missing: [], maybe_done: [] }))).toBeNull();
    expect(driftChip(plan({ level: "none", commits: 0, missing: [], maybe_done: [] }))).toBeNull();
  });

  it("tints only plans that need a second look", () => {
    expect(driftChip(plan({ level: "fresh", commits: 0, missing: [], maybe_done: [] }))?.variant).toBe("outline");
    expect(driftChip(plan({ level: "drifted", commits: 1, missing: [], maybe_done: [] }))?.text).toBe("1 commit since");
    expect(driftChip(plan({ level: "stale", commits: 0, missing: ["a.py"], maybe_done: [] }))?.variant).toBe("warn");
    expect(driftChip(plan({ level: "maybe-done", commits: 2, missing: [], maybe_done: ["abc feat: x"] }))?.text).toBe("May be done");
  });
});
