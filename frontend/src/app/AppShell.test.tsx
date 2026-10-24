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
  getShareStatus: async () => ({ status: null, chip: null }),
  getGraphNodes: async () => [],
});

describe("AppShell", () => {
  it("has one nav, one theme toggle, and a palette that navigates", async () => {
    const router = createAppRouter(createMemoryHistory({ initialEntries: ["/app/ops"] }));
    render(<App source={ds} router={router} />);
    const nav = await screen.findByRole("navigation", { name: "Main" });
    expect(nav.querySelectorAll("a")).toHaveLength(ROUTES.length);
    expect(nav).toHaveClass("overflow-x-auto", "min-w-0"); // scrolls inside itself on phones
    expect(screen.getAllByRole("button", { name: /switch to/i })).toHaveLength(1);
    expect(await screen.findByRole("link", { name: /open the legacy page/i })).toHaveAttribute("href", "/legacy/ops");

    await userEvent.keyboard("{Control>}k{/Control}");
    const box = await screen.findByPlaceholderText("Go to…");
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
