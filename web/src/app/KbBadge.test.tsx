import { createMemoryHistory } from "@tanstack/react-router";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useHeaderFold } from "@/app/headerFold";
import { App } from "@/app/providers";
import { createAppRouter } from "@/app/router";
import type { DataSource } from "@/api";
import type { KbInfo, KbList } from "@/api/types";
import { sampleSnapshot } from "@/features/graph/fixtures";
import { withFlag } from "@/flags/testing";
import { mockDataSource } from "@/test/datasource";

// the menu drives the graph screen; its canvas needs a real 2D context, which jsdom has not
vi.mock("@/features/graph/GraphCanvas", async () => {
  const { forwardRef } = await import("react");
  return { GraphCanvas: forwardRef(() => <div data-testid="canvas" />) };
});

const git = { repo: true, branch: "main" } as KbList["kbs"][number]["git"];
const row = (id: string, name: string, active = false) => ({ id, name, root: `/b/${id}`, schema_version: "1.3", error: "", active, git });
const list = (extra: ReturnType<typeof row>[] = []): KbList => ({
  bases_dir: "/b", think_root: "/t", active: "alpha",
  kbs: [row("alpha", "Alpha", true), row("beta", "Beta"), ...extra],
});
const info = { id: "alpha", name: "Alpha", root: "/b/alpha", git } as unknown as KbInfo;

function open(path: string, over: Partial<DataSource> = {}) {
  const graphs: (readonly string[] | undefined)[] = [];
  const ds: Partial<DataSource> = {
    getKb: async () => info,
    listKbs: async () => list(),
    getGraph: async (o) => (graphs.push(o?.kbs), sampleSnapshot()),
    getShareStatus: async () => ({ status: null, chip: null }),
    getGraphNodes: async () => [],
    ...over,
  };
  const router = createAppRouter(createMemoryHistory({ initialEntries: [path] }), "");
  render(<App source={mockDataSource(ds)} router={router} />);
  return { router, graphs };
}

describe("header knowledge base menu (kb-view)", () => {
  // these tests read the app bar itself, so keep it open on the graph (flag header-fold folds it by default)
  beforeEach(() => {
    localStorage.clear();
    useHeaderFold.setState({ folded: false });
  });

  it("flag on: ticks show more knowledge bases, and unticking all shows none", () =>
    withFlag("kb-view", true, async () => {
      const { router } = open("/graph");
      await userEvent.click(await screen.findByRole("button", { name: "Knowledge bases" }));
      const beta = await screen.findByRole("checkbox", { name: /Beta/ });
      await userEvent.click(beta);
      await waitFor(() => expect(router.state.location.search).toMatchObject({ kbs: "alpha,beta" }));
      await userEvent.click(screen.getByRole("checkbox", { name: /Alpha/ }));
      await userEvent.click(screen.getByRole("checkbox", { name: /Beta/ }));
      await waitFor(() => expect(router.state.location.search).toMatchObject({ kbs: "none" }));
      expect(await screen.findByText(/No knowledge base is shown/)).toBeInTheDocument();
    }));

  it("lists the knowledge bases of the bases dir and offers no add-folder form (one discovery path)", () =>
    withFlag("kb-view", true, async () => {
      open("/graph");
      await userEvent.click(await screen.findByRole("button", { name: "Knowledge bases" }));
      const menu = await screen.findByRole("dialog", { name: /Knowledge bases on the graph/ });
      expect(within(menu).getAllByRole("checkbox")).toHaveLength(2);
      expect(within(menu).queryByLabelText(/Add a folder/)).toBeNull();
      expect(within(menu).queryByRole("button", { name: /^Add$/ })).toBeNull();
    }));

  it("flag off: the title is the plain link to System → Knowledge bases", () =>
    withFlag("kb-view", false, async () => {
      open("/graph?kbs=beta");
      expect(await screen.findByRole("link", { name: "Knowledge base" })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Knowledge bases" })).toBeNull();
    }));
});

describe("header title without an import adapter", () => {
  it("a build that is not the private share profile shows no add button", async () => {
    const ds = { ...mockDataSource({ getShareStatus: async () => ({ status: null, chip: null }) }), kind: "embedded" } as DataSource;
    render(<App source={ds} router={createAppRouter(createMemoryHistory({ initialEntries: ["/"] }), "")} />);
    await screen.findByRole("banner");
    expect(screen.queryByRole("button", { name: "Add knowledge base" })).toBeNull();
  });
});
