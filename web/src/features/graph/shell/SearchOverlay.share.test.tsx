import { createMemoryHistory } from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createEmbeddedDataSource, type DataSource } from "@/api";
import { withFlag } from "@/flags/testing";
import { App } from "@/app/providers";
import { resetEmbed } from "@/app/embed";
import { createAppRouter } from "@/app/router";
import { useUi } from "@/app/ui-store";
import type { ShareBlob } from "@/share/blob";
import { node } from "../fixtures";
import { useShellStore } from "./shellStore";

vi.mock("@/share/env", () => ({ IS_SHARE: true, SHARE_PROFILE: "private" }));

const nodes = [node("margin-theory", { title: "Margin theory", inDegree: 3 }), node("kernel", { title: "Kernel methods" })];
const blob = {
  graph: { nodes, links: [] },
  index: { pages: [] },
  pages: {},
  views: [{ id: "mine", name: "My orphans", created: "2026-11-01", spec: { v: 1, types: "all" } }],
  readyViews: [],
  favorites: [],
} as unknown as ShareBlob;

describe("Cmd+K on the shared site (graph-intent on)", () => {
  beforeEach(() => {
    resetEmbed();
    useUi.setState({ lineOpen: false, paletteOpen: false, captureOpen: false });
    useShellStore.setState({ pendingLine: null, pendingView: null });
  });

  it("searches pages and lists saved views; > searches instead with the copy; no Ask row, no model, no write", () =>
    withFlag("graph-intent", true, async () => {
      const fetchSpy = vi.fn(async (_url: unknown, _init?: RequestInit) => new Response("{}", { status: 404 }));
      vi.stubGlobal("fetch", fetchSpy);
      const layersFromText = vi.fn();
      const ds = { ...createEmbeddedDataSource(blob), getGraph: (async () => ({ nodes, links: [] })) as never, layersFromText } as unknown as DataSource;
      const router = createAppRouter(createMemoryHistory({ initialEntries: ["/"] }));
      render(<App source={ds} router={router} />);
      await waitFor(() => expect(document.body).toBeTruthy());
      await userEvent.keyboard("{Control>}k{/Control}");
      const box = await screen.findByRole("combobox");
      expect(box.getAttribute("placeholder")).toBe("Search everything · / commands");
      await userEvent.type(box, "marg");
      expect(await screen.findByRole("option", { name: /Margin theory/ })).toBeInTheDocument();
      expect(screen.queryByRole("option", { name: /Ask the agent/ })).toBeNull();
      await userEvent.clear(box);
      expect(await screen.findByRole("option", { name: /My orphans/ })).toBeInTheDocument();
      await userEvent.type(box, "> kern");
      expect(await screen.findByText("Changing the view is not available here")).toBeInTheDocument();
      expect(screen.queryByRole("option", { name: /Change the view on the graph/ })).toBeNull();
      expect(await screen.findByRole("option", { name: /Kernel methods/ })).toBeInTheDocument();
      await userEvent.keyboard("{Enter}");
      expect(layersFromText).not.toHaveBeenCalled();
      expect(fetchSpy.mock.calls.filter(([, i]) => i?.method)).toEqual([]);
      vi.unstubAllGlobals();
    }));
});
