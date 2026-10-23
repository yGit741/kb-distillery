import { createMemoryHistory } from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "./providers";
import { createAppRouter } from "./router";
import type { DataSource } from "@/api";
import { ROUTES } from "@/routes/registry";

const ds: DataSource = {
  kind: "http",
  getLifecycle: () => new Promise(() => {}),
  getShareStatus: async () => ({ status: null, chip: null }),
  getGraphNodes: async () => [],
};

describe("AppShell", () => {
  it("has one nav, one theme toggle, and a palette that navigates", async () => {
    const router = createAppRouter(createMemoryHistory({ initialEntries: ["/graph"] }));
    render(<App source={ds} router={router} />);
    const nav = await screen.findByRole("navigation", { name: "Main" });
    expect(nav.querySelectorAll("a")).toHaveLength(ROUTES.length);
    expect(screen.getAllByRole("button", { name: /switch to/i })).toHaveLength(1);
    expect(await screen.findByRole("link", { name: /open the legacy page/i })).toHaveAttribute("href", "/legacy/graph");

    await userEvent.keyboard("{Control>}k{/Control}");
    const box = await screen.findByPlaceholderText("Go to…");
    await userEvent.type(box, "lifecycle");
    await userEvent.keyboard("{Enter}");
    await waitFor(() => expect(router.state.location.pathname).toBe("/lifecycle"));
  });
});
