import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataSourceProvider, createEmbeddedDataSource, type DataSource } from "@/api";
import { withFlag } from "@/flags/testing";
import type { ShareBlob } from "@/share/blob";
import { sampleNodes, sampleSnapshot } from "../../fixtures";
import { parseSchema } from "../../schema";
import { DEFAULT_PREFS, useGraphUi } from "../../store";
import { Corners } from "./Corners";
import { resetCorners } from "./cornersStore";
import { resetGallery } from "../../views/galleryStore";

vi.mock("@/share/env", () => ({ IS_SHARE: true, SHARE_PROFILE: "private" }));

const schema = parseSchema(sampleSnapshot().schema);
const visible = new Set(sampleNodes.map((n) => n.id));
const blob = {
  graph: { nodes: sampleNodes, links: [] },
  index: { pages: [] },
  pages: {},
  views: [{ id: "mine", name: "My orphans", created: "2026-11-01", spec: { v: 1, types: "all" } }],
  readyViews: [],
  favorites: [],
} as unknown as ShareBlob;

function mount() {
  const fetchSpy = vi.fn(async () => new Response("{}", { status: 404 }));
  vi.stubGlobal("fetch", fetchSpy);
  const source: DataSource = createEmbeddedDataSource(blob);
  render(
    <DataSourceProvider source={source}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <div style={{ position: "relative", width: 1200, height: 800 }}>
          <Corners nodes={sampleNodes} visible={visible} schema={schema} shownTypes={new Set(schema.defaultVisible)} stats="" host={{ go: vi.fn(), href: (to: string) => to, openPage: vi.fn() }} applyView={vi.fn()} showPicked={vi.fn()} />
        </div>
      </QueryClientProvider>
    </DataSourceProvider>,
  );
  return fetchSpy;
}

beforeEach(() => {
  resetCorners();
  resetGallery();
  useGraphUi.setState({ ...DEFAULT_PREFS, story: "", shownTypes: undefined, predicate: null, shownDepths: null, hiddenKeys: new Set(), spotlight: null, view: null });
});
afterEach(() => vi.unstubAllGlobals());

describe("the pin corner on the shared site (graph-intent on)", () => {
  it("lists the saved views read-only: nothing to pin, rename, unpin or step back through, and no Think or Agent corner", async () => {
    await withFlag("graph-intent", true, async () => {
      const fetchSpy = mount();
      await userEvent.click(screen.getByRole("button", { name: "Saved views" }));
      expect(await screen.findByText("My orphans")).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Pin this view" })).toBeNull();
      expect(screen.queryByRole("button", { name: /options/i })).toBeNull();
      expect(screen.queryByText(/steps/i)).toBeNull();
      expect(screen.queryByRole("button", { name: "Think notes" })).toBeNull();
      expect(screen.queryByRole("button", { name: "Agent chats" })).toBeNull();
      expect(fetchSpy).not.toHaveBeenCalled();
    });
  });

  it("with graph-intent off there is no pin corner at all, as before", async () => {
    await withFlag("graph-intent", false, async () => {
      mount();
      expect(screen.queryByRole("button", { name: "Saved views" })).toBeNull();
      expect(screen.queryByRole("button", { name: "Pinned views" })).toBeNull();
    });
  });
});
