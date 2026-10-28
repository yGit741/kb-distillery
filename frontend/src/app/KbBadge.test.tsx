import { createMemoryHistory } from "@tanstack/react-router";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "@/app/providers";
import { createAppRouter } from "@/app/router";
import { ApiError, type DataSource } from "@/api";
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
const row = (id: string, name: string, active = false) => ({ id, name, root: `/b/kb-${id}`, schema_version: "1.3", error: "", active, git });
const list = (extra: ReturnType<typeof row>[] = []): KbList => ({
  bases_dir: "/b", registry: "/r", registry_exists: false, think_root: "/t", active: "alpha",
  kbs: [row("alpha", "Alpha", true), row("beta", "Beta"), ...extra],
});
const info = { id: "alpha", name: "Alpha", root: "/b/kb-alpha", git } as unknown as KbInfo;

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
  beforeEach(() => localStorage.clear());

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

  it("adds a folder from disk and shows it; a refused folder shows why", () =>
    withFlag("kb-view", true, async () => {
      let calls = 0;
      const { router } = open("/graph", {
        registerKb: async (path) => {
          calls++;
          if (path.includes("bad")) throw new ApiError("/x is not a git repository", 400);
          return list([row("far", "Far")]);
        },
      });
      await userEvent.click(await screen.findByRole("button", { name: "Knowledge bases" }));
      const input = await screen.findByLabelText(/Add a folder/);
      await userEvent.type(input, "/somewhere/bad");
      await userEvent.click(screen.getByRole("button", { name: /^Add$/ }));
      const menu = screen.getByRole("dialog", { name: /Knowledge bases on the graph/ });
      expect(await within(menu).findByRole("alert")).toHaveTextContent("not a git repository");
      await userEvent.clear(input);
      await userEvent.type(input, "/somewhere/far");
      await userEvent.click(screen.getByRole("button", { name: /^Add$/ }));
      await waitFor(() => expect(router.state.location.search).toMatchObject({ kbs: "alpha,far" }));
      expect(calls).toBe(2);
    }));

  it("flag off: the title is the plain link to System → Knowledge bases", () =>
    withFlag("kb-view", false, async () => {
      open("/graph?kbs=beta");
      expect(await screen.findByRole("link", { name: "Knowledge base" })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Knowledge bases" })).toBeNull();
    }));
});
