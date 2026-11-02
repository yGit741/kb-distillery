import { createMemoryHistory } from "@tanstack/react-router";
import { render, screen, within } from "@testing-library/react";
import { App } from "@/app/providers";
import { createAppRouter } from "@/app/router";
import { ApiError, type DataSource, type LifecycleSnapshot } from "@/api";
import { mockDataSource } from "@/test/datasource";
import { nowCards } from "./StartScreen";

const snap = {
  version: "0.13.1",
  snapshots: [{ tag: "kb-0.13.0", date: "2026-10-23", label: "baseline" }],
  working: { lanes: { knowledge: 2, tooling: 0 }, sessions: { ingest: [{}], distill: [], researcher: [], ops: { op: "refine" } } },
  infra_branches: [{ name: "infra/a" }, { name: "infra/b" }],
} as unknown as LifecycleSnapshot;

function open(over: Partial<DataSource> = {}) {
  const router = createAppRouter(createMemoryHistory({ initialEntries: ["/start"] }), "");
  render(
    <App
      source={mockDataSource({
        getLifecycle: async () => snap,
        getShareStatus: async () => ({ status: null, chip: null }),
        getGraphNodes: async () => [],
        ...over,
      })}
      router={router}
    />,
  );
}

describe("Start screen", () => {
  it("lists the same sections as the legacy Start page", async () => {
    open();
    expect(await screen.findByRole("heading", { name: "Start here" })).toBeInTheDocument();
    for (const title of [
      "Three places, three owners",
      "Edit knowledge",
      "Develop a feature",
      "Commit names at a glance",
      "Daily rhythm",
      "Rules that protect you",
    ])
      expect(screen.getByText(title)).toBeInTheDocument();
    for (const id of ["raw", "wiki", "think"]) expect(screen.getByTestId(`place-${id}`)).toBeInTheDocument();
  });

  it("the edit table keeps every group and the skill for each phrase", async () => {
    open();
    await screen.findByText("Edit knowledge");
    for (const g of ["Bring sources in", "Write notes", "Shape the graph", "Your own thinking", "Use, check, go back"])
      expect(screen.getByText(g)).toBeInTheDocument();
    expect(screen.getAllByRole("row").length).toBeGreaterThanOrEqual(25);
    const row = screen.getByText("Save a paper, link or file").closest("tr")!;
    expect(within(row).getByText("scrap <url>")).toBeInTheDocument();
    expect(within(row).getByText("scrap-data")).toBeInTheDocument();
    expect(within(row).getByText("kb(import)")).toBeInTheDocument();
    expect(screen.getByText(/never picks full on its own/)).toHaveAttribute("colspan", "3");
  });

  it("links to the Lifecycle screen", async () => {
    open();
    const links = await screen.findAllByRole("link", { name: "Lifecycle" });
    expect(links.length).toBeGreaterThanOrEqual(2);
    expect(links[0]).toHaveAttribute("href", "/lifecycle");
  });

  it("shows the right-now cards from the lifecycle snapshot", async () => {
    open();
    const now = await screen.findByTestId("now");
    expect(now).toHaveTextContent("Knowledge versionkb-0.13.1");
    expect(now).toHaveTextContent("Last snapshotkb-0.13.0");
    expect(now).toHaveTextContent("Open sessions2");
    expect(now).toHaveTextContent("Uncommitted knowledge2");
    expect(now).toHaveTextContent("Open feature branches2");
  });

  it("a shared snapshot has no working state: only version and snapshot, plus branches when present", () => {
    const shared = { ...snap, working: undefined, infra_branches: undefined, snapshots: [], version: "" } as unknown as LifecycleSnapshot;
    expect(nowCards(shared)).toEqual([["Knowledge version", "none yet"], ["Last snapshot", "none"]]);
  });

  it("shows a loading state, and an error that does not hide the static guide", async () => {
    open({ getLifecycle: () => Promise.reject(new ApiError("boom", 500)) });
    expect(await screen.findByRole("status", { name: /loading the current state/i })).toBeInTheDocument();
    expect(await screen.findByText(/could not load the current state/i, {}, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.getByText("Edit knowledge")).toBeInTheDocument();
  });
});
