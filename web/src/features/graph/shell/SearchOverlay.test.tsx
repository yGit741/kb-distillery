import { createMemoryHistory } from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { DataSource } from "@/api";
import { withFlag } from "@/flags/testing";
import { node } from "../fixtures";
import { useShellStore } from "./shellStore";
import { mockDataSource } from "@/test/datasource";
import { App } from "@/app/providers";
import { resetEmbed } from "@/app/embed";
import { createAppRouter } from "@/app/router";
import { useUi } from "@/app/ui-store";

const nodes = [
  node("margin-theory", { title: "Margin theory", inDegree: 3 }),
  node("margin-thoughts", { title: "Margin thoughts", type: "think-note" }),
  node("kernel", { title: "Kernel methods" }),
];
const ds: DataSource = mockDataSource({
  getLifecycle: () => new Promise(() => {}),
  getOps: () => new Promise(() => {}),
  getHealth: () => new Promise(() => {}),
  getShareStatus: async () => ({ status: null, chip: null }),
  getGraph: (async () => ({ nodes, links: [] })) as never,
  getGraphNodes: async () => [],
  search: (async () => ({ hits: [], total: 0 })) as never,
  listRecent: async () => ({ recent: [] }),
  listViews: async () => ({ views: [] }),
});

function mount(path = "/app/system") {
  const router = createAppRouter(createMemoryHistory({ initialEntries: [path] }));
  const view = render(<App source={ds} router={router} />);
  return { router, ...view };
}
const line = () => screen.findByRole("combobox");
const key = (k: string) => userEvent.keyboard(`{Control>}${k}{/Control}`);

beforeEach(() => {
  resetEmbed();
  useUi.setState({ lineOpen: false, paletteOpen: false, captureOpen: false });
  useShellStore.setState({ pendingLine: null, pendingView: null });
});

describe("the search line on every screen (flag graph-intent)", () => {
  it("Cmd/Ctrl+K opens the overlay on a non-graph route and Escape closes it", () =>
    withFlag("graph-intent", true, async () => {
      mount();
      await screen.findByRole("tablist", { name: "System sections" });
      await key("k");
      expect(await screen.findByTestId("search-overlay")).toBeInTheDocument();
      expect(await line()).toHaveFocus();
      await userEvent.keyboard("{Escape}");
      await waitFor(() => expect(screen.queryByTestId("search-overlay")).toBeNull());
    }));

  it("does not open while typing in a textarea", () =>
    withFlag("graph-intent", true, async () => {
      mount();
      await screen.findByRole("tablist", { name: "System sections" });
      const area = document.createElement("textarea");
      document.body.append(area);
      area.focus();
      await key("k");
      expect(screen.queryByTestId("search-overlay")).toBeNull();
      area.remove();
    }));

  it("Enter on a page row opens the page", () =>
    withFlag("graph-intent", true, async () => {
      const { router } = mount();
      await screen.findByRole("tablist", { name: "System sections" });
      await key("k");
      await userEvent.type(await line(), "margin theory");
      await screen.findByRole("option", { name: /Margin theory/ });
      await userEvent.keyboard("{Enter}");
      await waitFor(() => expect(router.state.location.pathname).toBe("/pages/margin-theory"));
      expect(screen.queryByTestId("search-overlay")).toBeNull();
    }));

  it("Shift+Enter goes to the graph and selects the page", () =>
    withFlag("graph-intent", true, async () => {
      const { router } = mount();
      await screen.findByRole("tablist", { name: "System sections" });
      await key("k");
      await userEvent.type(await line(), "margin theory");
      await screen.findByRole("option", { name: /Margin theory/ });
      await userEvent.keyboard("{Shift>}{Enter}{/Shift}");
      await waitFor(() => expect(router.state.location.pathname).toBe("/graph"));
      expect(router.state.location.search).toMatchObject({ select: "margin-theory", focus: "margin-theory" });
    }));

  it("a > sentence is handed to the graph through pendingLine", () =>
    withFlag("graph-shell", false, () => withFlag("graph-intent", true, async () => {
      const { router } = mount();
      await screen.findByRole("tablist", { name: "System sections" });
      await key("k");
      await userEvent.type(await line(), ">colour by area");
      await userEvent.keyboard("{Enter}");
      await waitFor(() => expect(router.state.location.pathname).toBe("/graph"));
      // no graph line is mounted in this test, so the text is still waiting for it
      expect(useShellStore.getState().pendingLine).toBe(">colour by area");
    })));

  it("/ lists the off-graph commands plus Open the graph, none of the graph-only ones", () =>
    withFlag("graph-intent", true, async () => {
      mount();
      await screen.findByRole("tablist", { name: "System sections" });
      await key("k");
      await userEvent.type(await line(), "/");
      expect(await screen.findByRole("option", { name: /Open the graph/ })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: /System: Health/ })).toBeInTheDocument();
      expect(screen.queryByRole("option", { name: /Fit to view/ })).toBeNull();
      expect(screen.queryByRole("option", { name: /Zoom in/ })).toBeNull();
      expect(screen.queryByRole("option", { name: /Reheat layout/ })).toBeNull();
    }));

  it("flag off: no overlay", () =>
    withFlag("graph-intent", false, async () => {
      mount();
      await screen.findByRole("tablist", { name: "System sections" });
      await key("k");
      expect(screen.queryByTestId("search-overlay")).toBeNull();
      expect(await screen.findByPlaceholderText(/^Go to…/)).toBeInTheDocument(); // the old palette
    }));
});
