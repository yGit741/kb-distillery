import { createMemoryHistory } from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "./providers";
import { resetEmbed } from "./embed";
import { createAppRouter } from "./router";
import type { DataSource } from "@/api";
import { withFlag } from "@/flags/testing";
import { mockDataSource } from "@/test/datasource";
import { ROUTES } from "@/routes/registry";

const ds: DataSource = mockDataSource({
  getLifecycle: () => new Promise(() => {}),
  getOps: () => new Promise(() => {}),
  getHealth: () => new Promise(() => {}),
  getShareStatus: async () => ({ status: null, chip: null }),
  getGraphNodes: async () => [],
});

describe("AppShell", () => {
  it("has one nav of five tabs, one theme toggle, and a palette that reaches every screen", () => withFlag("views-panel", false, async () => {
    const router = createAppRouter(createMemoryHistory({ initialEntries: ["/app/system"] }));
    render(<App source={ds} router={router} />);
    const nav = await screen.findByRole("navigation", { name: "Main" });
    expect([...nav.querySelectorAll("a")].map((a) => a.textContent)).toEqual(["Home", "Graph", "System", "Chat", "Think"]);
    expect(ROUTES.length).toBeGreaterThan(3); // the rest stay routable
    expect(nav).toHaveClass("overflow-x-auto", "min-w-0"); // scrolls inside itself on phones
    expect(screen.getAllByRole("button", { name: /switch to/i })).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Tours" })).toBeInTheDocument(); // left of the palette chip, on every screen
    expect(await screen.findByRole("tablist", { name: "System sections" })).toBeInTheDocument();

    await userEvent.keyboard("{Control>}k{/Control}");
    const box = await screen.findByPlaceholderText(/^Go to…/);
    await userEvent.type(box, "pages");
    await userEvent.keyboard("{Enter}");
    await waitFor(() => expect(router.state.location.pathname).toBe("/pages"));
  }));

  it("flag views-panel: the header's theme toggle moves to the graph panel (hidden here); off, it stays", async () => {
    for (const on of [true, false]) {
      await withFlag("views-panel", on, async () => {
        const router = createAppRouter(createMemoryHistory({ initialEntries: ["/app/system"] }));
        const { unmount } = render(<App source={ds} router={router} />);
        await screen.findByRole("navigation", { name: "Main" });
        expect(screen.queryAllByRole("button", { name: /switch to/i })).toHaveLength(on ? 0 : 1);
        unmount();
      });
    }
  });

  it("sends the folded Pipeline and Lifecycle screens to their System tabs, search kept", async () => {
    for (const [from, tab] of [["/app/pipeline?q=raw%2Fa.pdf", "pipeline"], ["/app/lifecycle", "history"]] as const) {
      const router = createAppRouter(createMemoryHistory({ initialEntries: [from] }));
      const { unmount } = render(<App source={ds} router={router} />);
      await waitFor(() => expect(router.state.location.pathname).toBe("/system"));
      expect(router.state.location.search).toMatchObject(from.includes("q=") ? { tab, q: "raw/a.pdf" } : { tab });
      unmount();
    }
  });

  it("sends the folded Relations, Scopes and Start screens to the graph tool or the Home card", async () => {
    for (const [from, to, search] of [
      ["/app/relations?min=90", "/graph", { tool: "relations", min: "90" }],
      ["/app/scopes", "/graph", { tool: "scopes" }],
      ["/app/start", "/", { start: true }],
    ] as const) {
      const router = createAppRouter(createMemoryHistory({ initialEntries: [from] }));
      const { unmount } = render(<App source={ds} router={router} />);
      await waitFor(() => expect(router.state.location.pathname).toBe(to));
      expect(router.state.location.search).toMatchObject(search);
      unmount();
    }
  });

  it("hides the header and nav with ?embed=1", async () => {
    resetEmbed();
    const router = createAppRouter(createMemoryHistory({ initialEntries: ["/app/pages?embed=1"] }));
    render(<App source={ds} router={router} />);
    await screen.findByRole("main");
    expect(screen.queryByRole("navigation", { name: "Main" })).toBeNull();
    resetEmbed();
  });
});
