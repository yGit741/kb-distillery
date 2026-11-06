import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { withFlag } from "@/flags/testing";
import { useKb } from "@/lib/store";
import { sampleLinks, sampleNodes } from "../fixtures";
import { Legend } from "../Legend";
import { parseSchema } from "../schema";
import { DEFAULT_PREFS, useGraphUi } from "../store";
import { Chips } from "./Chips";
import { EMPTY_STACK, makeLayer } from "./model";
import { useLayers } from "./store";

const byId = new Map(sampleNodes.map((n) => [n.id, n] as const));
const show = vi.fn();

beforeEach(() => {
  window.localStorage.clear();
  show.mockClear();
  useLayers.setState({ stack: EMPTY_STACK, history: [], future: [], applied: null, skipped: [], graph: { nodes: sampleNodes, links: sampleLinks, show } });
  useGraphUi.setState({ ...DEFAULT_PREFS, view: null, hiddenKeys: new Set(), hiddenLinkKinds: new Set(), flyout: null });
  useKb.getState().clearSelection();
});

describe("Chips", () => {
  it("renders nothing while both rows are empty", () => {
    render(<Chips byId={byId} />);
    expect(screen.queryByTestId("chip-rows")).not.toBeInTheDocument();
  });

  it("shows the focus row, and remove deselects", async () => {
    useKb.getState().setSelection(["idea-margin", "jane-doe"]);
    render(<Chips byId={byId} />);
    const row = screen.getByRole("group", { name: "Focus" });
    expect(within(row).getByText("idea margin")).toBeInTheDocument();
    await userEvent.click(within(row).getByRole("button", { name: /remove idea margin/i }));
    expect([...useKb.getState().selection]).toEqual(["jane-doe"]);
    expect(screen.queryByRole("group", { name: "View" })).not.toBeInTheDocument();
  });

  it("shows one View chip per layer in plain words, and remove drops the layer", async () => {
    useLayers.getState().apply("replace", [makeLayer("show", "nodes", { nodes: [{ t: "type", value: "paper" }] }, "only papers")]);
    useLayers.getState().apply("stack", [makeLayer("hide", "edges", { edges: [{ t: "type", value: "MENTIONS" }] })]);
    render(<Chips byId={byId} />);
    const row = screen.getByRole("group", { name: "View" });
    expect(within(row).getByText("only papers")).toBeInTheDocument();
    expect(within(row).getByText("Hide links: MENTIONS links")).toBeInTheDocument();
    await userEvent.click(within(row).getByRole("button", { name: "Remove only papers" }));
    expect(within(row).queryByText("only papers")).not.toBeInTheDocument();
    expect(useLayers.getState().stack.layers).toHaveLength(1);
  });

  it("an Undo control appears with history and takes the last change back", async () => {
    useLayers.getState().apply("replace", [makeLayer("show", "nodes", { nodes: [{ t: "type", value: "paper" }] }, "only papers")]);
    render(<Chips byId={byId} />);
    await userEvent.click(screen.getByRole("button", { name: /undo/i }));
    expect(useLayers.getState().stack.layers).toHaveLength(0);
    expect(screen.queryByText("only papers")).not.toBeInTheDocument();
  });

  it("clicking a chip opens an inline editor for its main parameter", async () => {
    useLayers.getState().apply("replace", [makeLayer("show", "nodes", { nodes: [{ t: "hops", of: "course-runi-rl", n: 1 }] })]);
    render(<Chips byId={byId} />);
    await userEvent.click(screen.getByRole("button", { name: /^Show pages: within 1 hop of course-runi-rl$/ }));
    const input = screen.getByLabelText("Hops");
    await userEvent.clear(input);
    await userEvent.type(input, "2{Enter}");
    expect(screen.getByText("Show pages: within 2 hops of course-runi-rl")).toBeInTheDocument();
    expect(screen.queryByLabelText("Hops")).not.toBeInTheDocument();
  });

  it("a chip with no parameter has no editor", () => {
    useLayers.getState().apply("replace", [makeLayer("show", "nodes", {}, "a sentence")]);
    render(<Chips byId={byId} />);
    expect(screen.queryByRole("button", { name: "a sentence" })).not.toBeInTheDocument();
  });
});

describe("Legend follows the stack", () => {
  const schema = parseSchema(undefined);
  const props = { nodes: sampleNodes, visible: new Set(sampleNodes.map((n) => n.id)), schema, shownTypes: null, stats: "7 pages" };
  const edgeStyle = () => useLayers.getState().apply("stack", [makeLayer("style", "edges", { edges: [{ t: "type", value: "MENTIONS" }] }, "", { style: { width: "thick" } })]);

  it("flag on: an edge style gets a row, and it leaves with its layer", () => {
    withFlag("graph-intent", true, () => {
      edgeStyle();
      render(<Legend {...props} />);
      const key = screen.getByTestId("stack-key");
      expect(within(key).getByText("Style links: width thick for MENTIONS links")).toBeInTheDocument();
      expect(within(key).getByText("Links")).toBeInTheDocument();
    });
  });

  it("flag on: a change by hand retires the rows", () => {
    withFlag("graph-intent", true, () => {
      edgeStyle();
      useGraphUi.setState({ sizeBy: "uniform" });
      render(<Legend {...props} />);
      expect(screen.queryByTestId("stack-key")).not.toBeInTheDocument();
    });
  });

  it("flag off: the legend is the same, whatever the stack holds", () => {
    withFlag("graph-intent", false, () => {
      edgeStyle();
      const { container } = render(<Legend {...props} />);
      expect(screen.queryByTestId("stack-key")).not.toBeInTheDocument();
      expect(screen.getByRole("group", { name: "Filters" })).toBeInTheDocument();
      expect(container.textContent).not.toMatch(/width thick/);
    });
  });
});
