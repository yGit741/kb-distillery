import { createMemoryHistory } from "@tanstack/react-router";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "@/app/providers";
import { createAppRouter } from "@/app/router";
import { ApiError, type DataSource } from "@/api";
import type { PageCard, PageDetail, PageIndex } from "@/api/types";
import { mockDataSource } from "@/test/datasource";

const card = (id: string, o: Partial<PageCard> = {}): PageCard => ({
  id, title: `Title ${id}`, type: "paper", status: "digested", depth: "full", areas: ["learning-theory"], preview: "p", words: 300, ...o,
});
const index: PageIndex = {
  generated_at: "t",
  pages: [card("alpha", { year: 2021 }), card("beta", { type: "topic", depth: "" }), card("gamma")],
  links: [["alpha", "beta"], ["gamma", "alpha"]],
  wanted: [],
  wanted_total: 0,
};
const detail: PageDetail = {
  card: index.pages[0]!,
  path: "wiki/paper-alpha.md",
  frontmatter: { url: "https://example.org/x", raw: "raw/printed-docs/2021-alpha.pdf", authors: ["A. Author"] },
  markdown: "# Title alpha\n\nSee [[beta]] and [[missing-page]]. $x^2$\n",
  backlinks: [{ id: "gamma", context: "gamma cites alpha" }],
  outbound: ["beta"],
  broken: ["missing-page"],
  suggested: [],
};

const base: Partial<DataSource> = {
  listPages: async () => index,
  getPage: async () => detail,
  search: async (q) => ({ query: q, total: 1, hits: [{ id: "alpha", title: "Title alpha", type: "paper", snippet: "about tensor rank", score: 9 }] }),
  findPath: async (a, b) => ({
    a, b, distance: 1,
    paths: [{ nodes: [a, b], hops: [{ from: a, to: b, dir: "forward", context: "alpha links beta" }] }],
  }),
  getShareStatus: async () => ({ status: null, chip: null }),
  getGraphNodes: async () => [],
};

function open(path: string, over: Partial<DataSource> = {}) {
  const router = createAppRouter(createMemoryHistory({ initialEntries: [path] }), "");
  render(<App source={mockDataSource({ ...base, ...over })} router={router} />);
  return router;
}

describe("Pages screen", () => {
  beforeEach(() => localStorage.clear());

  it("shows the home overview from the index", async () => {
    open("/pages");
    expect(await screen.findByRole("heading", { name: "Pages" })).toBeInTheDocument();
    expect(screen.getByText(/3 pages/)).toBeInTheDocument();
  });

  it("reads a page: facts as badges, raw link, wikilinks, wanted links, collapsed neighbours", async () => {
    open("/pages/alpha");
    expect(await screen.findByRole("heading", { level: 1, name: "Title alpha" })).toBeInTheDocument();
    const facts = screen.getByLabelText("Page facts");
    expect(within(facts).getByText("source")).toBeInTheDocument();
    expect(within(facts).getByText("paper")).toBeInTheDocument();
    expect(within(facts).getByText("full")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "raw/printed-docs/2021-alpha.pdf" })).toHaveAttribute("href", expect.stringContaining("/pipeline"));
    expect(screen.getAllByRole("link", { name: "Title beta" })[0]).toHaveAttribute("href", "/pages/beta");
    expect(screen.getByText("missing-page", { selector: ".wikilink" })).toHaveAttribute("data-missing", "true");
    const linkedFrom = screen.getByText("Linked from").closest("details")!;
    expect(linkedFrom).not.toHaveAttribute("open");
    expect(screen.getByRole("group", { name: "Neighbour graph" })).toBeInTheDocument();
  });

  it("records the trail and toggles a pin", async () => {
    open("/pages/alpha");
    await screen.findByRole("heading", { level: 1, name: "Title alpha" });
    await waitFor(() => expect(JSON.parse(localStorage.getItem("explore-trail") ?? "[]")).toEqual(["alpha"]));
    await userEvent.click(screen.getByRole("button", { name: /^pin$/i }));
    expect(JSON.parse(localStorage.getItem("explore-pins") ?? "[]")).toEqual(["alpha"]);
    expect(screen.getByRole("button", { name: /unpin/i })).toHaveAttribute("aria-pressed", "true");
  });

  it("runs the full-text search from ?q=", async () => {
    open("/pages?q=tensor");
    expect(await screen.findByText(/1 page/)).toBeInTheDocument();
    expect(screen.getByText("tensor", { selector: "mark" })).toBeInTheDocument();
  });

  it("finds a path between two pages", async () => {
    open("/pages/alpha");
    await screen.findByRole("heading", { level: 1, name: "Title alpha" });
    await userEvent.click(screen.getByRole("button", { name: "Connect to…" }));
    await userEvent.type(screen.getByLabelText("To page"), "beta");
    await userEvent.click(screen.getByRole("button", { name: "Find path" }));
    expect(await screen.findByText("alpha links beta")).toBeInTheDocument();
    expect(screen.getByText(/1 hop/)).toBeInTheDocument();
  });

  it("redirects old #/p/slug links", async () => {
    window.location.hash = "#/p/beta";
    const router = open("/pages");
    await waitFor(() => expect(router.state.location.pathname).toBe("/pages/beta"));
    window.location.hash = "";
  });

  it("shows a missing-page message on 404 and an error with retry otherwise", async () => {
    open("/pages/ghost", { getPage: async () => { throw new ApiError("not found", 404); } });
    expect(await screen.findByText(/No page/)).toBeInTheDocument();
  });

  it("shows an error with retry when the index fails", { timeout: 15_000 }, async () => {
    open("/pages", { listPages: async () => { throw new Error("boom"); } });
    expect(await screen.findByRole("alert", {}, { timeout: 10_000 })).toHaveTextContent("Could not load the page index.");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("embed mode hides the toolbar and trail but keeps the content", async () => {
    window.history.replaceState({}, "", "/?embed=1");
    open("/pages/alpha");
    expect(await screen.findByRole("heading", { level: 1, name: "Title alpha" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Search pages")).toBeNull();
    expect(screen.queryByRole("button", { name: "Connect to…" })).toBeNull();
    expect(screen.getByText("Linked from")).toBeInTheDocument();
    window.history.replaceState({}, "", "/");
  });
});
