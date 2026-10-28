import { createMemoryHistory } from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import { App } from "@/app/providers";
import { createAppRouter } from "@/app/router";
import type { DataSource } from "@/api";
import type { KbList, PageCard, PageDetail, PageIndex } from "@/api/types";
import { resetEmbed } from "@/app/embed";
import { withFlag } from "@/flags/testing";
import { mockDataSource } from "@/test/datasource";

const card = (id: string): PageCard => ({ id, title: `Title ${id}`, type: "idea", status: "", depth: "", areas: [], preview: "p", words: 10 });
const index: PageIndex = { generated_at: "t", pages: [card("shared"), card("note")], links: [["shared", "note"]], wanted: [], wanted_total: 0 };
const detail = (kb: string, readOnly: boolean): PageDetail => ({
  card: card("shared"), path: "wiki/shared.md", frontmatter: {}, markdown: "# Title shared\n\nSee [[note]].\n",
  backlinks: [], outbound: ["note"], broken: [], suggested: [], kb, read_only: readOnly,
});
const kbs: KbList = {
  bases_dir: "/b", registry: "/r", registry_exists: false, think_root: "/t", active: "alpha",
  kbs: [
    { id: "alpha", name: "Alpha", root: "/b/kb-alpha", schema_version: "1.3", error: "", active: true, git: { repo: false } as KbList["kbs"][number]["git"] },
    { id: "beta", name: "Beta", root: "/b/kb-beta", schema_version: "1.3", error: "", active: false, git: { repo: false } as KbList["kbs"][number]["git"] },
  ],
};

function open(path: string, calls: { kb?: string }[]) {
  const ds: Partial<DataSource> = {
    listPages: async (o) => (calls.push({ kb: o?.kb }), index),
    getPage: async (_s, o) => detail(o?.kb ?? "alpha", !!o?.kb && o.kb !== "alpha"),
    listKbs: async () => kbs,
    getShareStatus: async () => ({ status: null, chip: null }),
    getGraphNodes: async () => [],
  };
  render(<App source={mockDataSource(ds)} router={createAppRouter(createMemoryHistory({ initialEntries: [path] }), "")} />);
}

describe("Pages of another knowledge base (kb-view)", () => {
  beforeEach(() => {
    localStorage.clear();
    resetEmbed();
  });

  it("flag on: reads the page view only, hides pin/connect/Obsidian, links keep ?kb=", () =>
    withFlag("kb-view", true, async () => {
      const calls: { kb?: string }[] = [];
      open("/pages/shared?kb=beta", calls);
      expect(await screen.findByText(/View only · Beta/)).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /Pin/ })).toBeNull();
      expect(screen.queryByRole("button", { name: /Connect to/ })).toBeNull();
      expect(screen.queryByText("Open in Obsidian")).toBeNull();
      const link = screen.getAllByRole("link", { name: "Title note" })[0]!;
      expect(link.getAttribute("href")).toContain("kb=beta");
      expect(calls.some((c) => c.kb === "beta")).toBe(true);
    }));

  it("flag off: ?kb= is ignored and the page is the server's own", () =>
    withFlag("kb-view", false, async () => {
      const calls: { kb?: string }[] = [];
      open("/pages/shared?kb=beta", calls);
      expect(await screen.findByRole("button", { name: /Pin/ })).toBeInTheDocument();
      expect(screen.queryByText(/View only/)).toBeNull();
      await waitFor(() => expect(calls.length).toBeGreaterThan(0));
      expect(calls.every((c) => c.kb === undefined)).toBe(true);
    }));
});
