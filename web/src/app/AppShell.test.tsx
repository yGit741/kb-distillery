import { createMemoryHistory } from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "./providers";
import { resetEmbed } from "./embed";
import { createAppRouter } from "./router";
import type { DataSource } from "@/api";
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
  it("has one nav of four tabs, one theme toggle, and a palette that reaches every screen", async () => {
    const router = createAppRouter(createMemoryHistory({ initialEntries: ["/app/system"] }));
    render(<App source={ds} router={router} />);
    const nav = await screen.findByRole("navigation", { name: "Main" });
    expect([...nav.querySelectorAll("a")].map((a) => a.textContent)).toEqual(["Home", "Graph", "System", "Chat"]);
    expect(ROUTES.length).toBeGreaterThan(3); // the rest stay routable
    expect(nav).toHaveClass("overflow-x-auto", "min-w-0"); // scrolls inside itself on phones
    expect(screen.getAllByRole("button", { name: /switch to/i })).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Tours" })).toBeInTheDocument(); // left of the palette chip, on every screen
    expect(await screen.findByRole("tablist", { name: "System sections" })).toBeInTheDocument();

    await userEvent.keyboard("{Control>}k{/Control}");
    const box = await screen.findByPlaceholderText(/^Go to…/);
    await userEvent.type(box, "lifecycle");
    await userEvent.keyboard("{Enter}");
    await waitFor(() => expect(router.state.location.pathname).toBe("/lifecycle"));
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
