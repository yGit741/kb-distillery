import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useKb } from "@/lib/store";
import { node } from "../fixtures";
import { buildNeighborMap } from "../graphData";
import { resetCorners, useCorners } from "../shell/corners/cornersStore";
import { useLayer } from "../layerStore";
import { useLayers } from "../layers/store";
import { useShellStore } from "../shell/shellStore";
import { useGraphUi } from "../store";
import { bulge, HealthDial, ringArc } from "./HealthDial";
import { HealthLayer } from "./HealthLayer";

const src = (id: string, type: string, depth: string) => node(id, { type, layer: "source", depth });
const nodes = [
  src("p-used", "paper", "full"),
  src("p-waiting", "paper", "listed"),
  src("p-loose", "paper", "easy"),
  src("v-used", "lecture", "full"),
  node("idea-a", { type: "idea" }),
  node("idea-b", { type: "idea" }),
];
const neighbors = buildNeighborMap([
  { source: "p-used", target: "idea-a" },
  { source: "p-used", target: "idea-b" },
  { source: "v-used", target: "idea-a" },
]);
const byId = new Map(nodes.map((n) => [n.id, n] as const));
const layer = () => render(<HealthLayer nodes={nodes} neighbors={neighbors} byId={byId} />);

beforeEach(() => {
  useLayers.setState({ stack: { v: 2, layers: [] }, history: [], future: [], graph: null });
  useKb.getState().clearSelection();
  useGraphUi.setState({ spotIds: null, readerSlug: null });
  resetCorners();
});
afterEach(() => vi.useRealTimers());

describe("the Health dial", () => {
  it("lists each source kind with its count and its open issues", () => {
    render(<HealthDial nodes={nodes} neighbors={neighbors} byId={byId} />);
    const dial = screen.getByRole("group", { name: "Sources by kind" });
    const kinds = within(dial).getAllByRole("button");
    expect(kinds.map((b) => b.getAttribute("data-kind"))).toEqual(["paper", "play"]);
    expect(kinds[0]).toHaveTextContent("Papers 3");
    expect(kinds[0]).toHaveTextContent("1 waiting, 1 feed no concept");
    expect(kinds[1]).toHaveTextContent("all in use");
    // one source is "1 source"
    expect(kinds[1]).toHaveAccessibleName("Lectures: 1 source, all in use. Show on the map");
    expect(kinds[0]).toHaveAccessibleName("Papers: 3 sources, 1 waiting, 1 feed no concept. Show on the map");
  });

  it("the ring draws what is in use and what feeds no concept; waiting stays the empty track", () => {
    render(<HealthDial nodes={nodes} neighbors={neighbors} byId={byId} />);
    const [papers, lectures] = screen.getAllByRole("button");
    expect(papers!.querySelector("[data-part=healthy]")).not.toBeNull();
    expect(papers!.querySelector("[data-part=unlinked]")).not.toBeNull();
    expect(lectures!.querySelector("[data-part=unlinked]")).toBeNull();
    // a whole ring is two half turns (one arc cannot close on itself); a part is one arc
    expect(ringArc(0, 1).match(/A/g)).toHaveLength(2);
    expect(ringArc(0, 0.25).match(/A/g)).toHaveLength(1);
  });

  it("resting on a kind lights the concepts it feeds, and leaving clears it", () => {
    vi.useFakeTimers();
    render(<HealthDial nodes={nodes} neighbors={neighbors} byId={byId} />);
    const lectures = screen.getAllByRole("button")[1]!;
    fireEvent.pointerEnter(lectures);
    expect(useGraphUi.getState().spotIds).toBeNull(); // not before the pointer settles
    act(() => void vi.advanceTimersByTime(130));
    expect([...useGraphUi.getState().spotIds!]).toEqual(["idea-a"]);
    fireEvent.pointerLeave(lectures);
    act(() => void vi.advanceTimersByTime(170));
    expect(useGraphUi.getState().spotIds).toBeNull();
  });

  it("is drawn as a dial only from three kinds on: an arc the rings sit on, deeper with more kinds", () => {
    const { container, unmount } = render(<HealthDial nodes={nodes} neighbors={neighbors} byId={byId} />);
    expect(container.querySelector("[data-part=dial-line]")).toBeNull(); // two kinds: a plain column
    unmount();
    const three = [...nodes, src("m1", "mail", "full")];
    const { container: c3 } = render(<HealthDial nodes={three} neighbors={neighbors} byId={new Map(three.map((n) => [n.id, n] as const))} />);
    expect(c3.querySelector("[data-part=dial-line]")).not.toBeNull();
    const [first, middle, lastOne] = [...c3.querySelectorAll<HTMLElement>("button[data-kind]")].map((b) => parseInt(b.style.marginLeft || "0", 10));
    expect(first).toBe(0);
    expect(lastOne).toBe(0);
    expect(middle).toBe(bulge(3));
    expect(bulge(2)).toBe(0);
    expect(bulge(10)).toBeGreaterThan(bulge(3));
  });

  it("steps aside while the pinned list or the agent fan is open", () => {
    render(<HealthDial nodes={nodes} neighbors={neighbors} byId={byId} />);
    act(() => useCorners.getState().toggle("pins"));
    expect(screen.getByRole("group", { name: "Sources by kind" })).toHaveClass("opacity-0", "pointer-events-none");
  });

  it("draws nothing for a knowledge base without sources", () => {
    const { container } = render(<HealthDial nodes={[node("idea-a")]} neighbors={new Map()} byId={new Map()} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("pressing a source kind", () => {
  it("draws the kind on the map: its digested sources and the concepts they feed, as one layer of the view", async () => {
    layer();
    await userEvent.click(screen.getByRole("button", { name: /^Papers/ }));
    const layers = useLayers.getState().stack.layers;
    expect(layers).toHaveLength(1);
    expect(layers[0]).toMatchObject({ kind: "show", target: "nodes", text: "Papers and the concepts they feed" });
    // p-loose feeds no concept and is drawn alone; p-waiting has nothing to show yet
    expect(layers[0]!.subgraph.nodes).toEqual([{ t: "name", slugs: ["p-used", "idea-a", "idea-b", "p-loose"] }]);
    // the dial stays: another kind is one press away, and undo goes back
    expect(screen.getByRole("group", { name: "Sources by kind" })).toBeInTheDocument();
    expect(useLayers.getState().history).toHaveLength(1);
  });

  it("the map is asked to draw exactly those pages, sources included, though the Health view draws concepts alone", async () => {
    const show = vi.fn();
    const links = ([["p-used", "idea-a"], ["p-used", "idea-b"], ["v-used", "idea-a"]] as const).map(([source, target]) => ({ source, target, kind: "wikilink" as const }));
    act(() => useLayers.getState().setGraph({ nodes, links, drawn: new Set(["idea-a", "idea-b"]), show }));
    layer();
    await userEvent.click(screen.getByRole("button", { name: /^Papers/ }));
    expect(show).toHaveBeenCalledTimes(1);
    expect([...show.mock.calls[0]![0]].sort()).toEqual(["idea-a", "idea-b", "p-loose", "p-used"]);
  });

  it("another kind replaces the first, and nothing is left selected", async () => {
    layer();
    await userEvent.click(screen.getByRole("button", { name: /^Papers/ }));
    act(() => useKb.getState().setSelection(["p-used"]));
    await userEvent.click(screen.getByRole("button", { name: /^Lectures/ }));
    const layers = useLayers.getState().stack.layers;
    expect(layers).toHaveLength(1);
    expect(layers[0]!.subgraph.nodes).toEqual([{ t: "name", slugs: ["v-used", "idea-a"] }]);
    expect(useKb.getState().selection.size).toBe(0);
  });

  it("a kind with nothing digested changes nothing", async () => {
    const lone = [src("m1", "mail", "listed")];
    render(<HealthLayer nodes={lone} neighbors={new Map()} byId={new Map(lone.map((n) => [n.id, n] as const))} />);
    await userEvent.click(screen.getByRole("button", { name: /^Mail/ }));
    expect(useLayers.getState().stack.layers).toHaveLength(0);
    expect(useShellStore.getState().notice?.text).toBe("Nothing in Mail is digested yet, so there is nothing to draw.");
  });

  it("pages added by hand for one kind do not carry over to the next", async () => {
    layer();
    act(() => {
      useGraphUi.setState({ revealed: new Set(["idea-b"]) });
      useLayer.getState().pushExpansion(["idea-b"]);
    });
    await userEvent.click(screen.getByRole("button", { name: /^Lectures/ }));
    expect(useGraphUi.getState().revealed.size).toBe(0);
    expect(useLayer.getState().expansions).toEqual([]);
  });
});
