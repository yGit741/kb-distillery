import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { node } from "../fixtures";
import { buildNeighborMap } from "../graphData";
import { resetCorners, useCorners } from "../shell/corners/cornersStore";
import { useGraphUi } from "../store";
import { bulge, HealthDial, ringArc } from "./HealthDial";
import { HealthLayer } from "./HealthLayer";
import { useHealth } from "./healthStore";

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
const support = new Map([["idea-a", 2], ["idea-b", 1]]);
const onRead = vi.fn();
const layer = () => render(<HealthLayer nodes={nodes} neighbors={neighbors} byId={byId} support={support} onRead={onRead} />);

beforeEach(() => {
  useHealth.setState({ inside: null });
  useGraphUi.setState({ spotIds: null, readerSlug: null });
  resetCorners();
  onRead.mockClear();
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

describe("inside a source kind", () => {
  it("pressing a kind opens its sources beside the concepts they feed, least supported first", async () => {
    layer();
    await userEvent.click(screen.getByRole("button", { name: /^Papers/ }));
    const view = screen.getByRole("region", { name: /papers: sources and the concepts they feed/i });
    expect(within(view).getByText(/3/)).toBeInTheDocument();
    expect([...view.querySelectorAll("[data-source]")].map((b) => b.getAttribute("data-source"))).toEqual(["p-used"]);
    expect([...view.querySelectorAll("[data-concept]")].map((b) => b.getAttribute("data-concept"))).toEqual(["idea-b", "idea-a"]);
    expect(view.querySelectorAll("[data-health=links] > svg path")).toHaveLength(2);
    expect(within(view.querySelector("[data-idle=Waiting]") as HTMLElement).getByRole("button")).toHaveTextContent("p waiting");
    expect(within(view.querySelector("[data-idle='Feed no concept']") as HTMLElement).getByRole("button")).toHaveTextContent("p loose");
    expect(screen.queryByRole("group", { name: "Sources by kind" })).toBeNull();
  });

  it("a row opens its page; Back and Esc return to the dial, but Esc first closes an open page", async () => {
    layer();
    await userEvent.click(screen.getByRole("button", { name: /^Papers/ }));
    await userEvent.click(screen.getByRole("button", { name: /idea b/i }));
    expect(onRead).toHaveBeenCalledWith("idea-b");
    act(() => useGraphUi.setState({ readerSlug: "idea-b" }));
    await userEvent.keyboard("{Escape}");
    expect(useHealth.getState().inside).toBe("paper");
    act(() => useGraphUi.setState({ readerSlug: null }));
    await userEvent.keyboard("{Escape}");
    expect(useHealth.getState().inside).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: /^Papers/ }));
    await userEvent.click(screen.getByRole("button", { name: "Health" }));
    expect(screen.getByRole("group", { name: "Sources by kind" })).toBeInTheDocument();
  });

  it("what needs care comes first, a few pages of each list, the rest on demand", async () => {
    const many = [...Array.from({ length: 7 }, (_, i) => src(`w${i}`, "paper", "listed")), src("p-used", "paper", "full"), node("idea-a", { type: "idea" })];
    render(<HealthLayer nodes={many} neighbors={neighbors} byId={new Map(many.map((n) => [n.id, n] as const))} support={support} onRead={onRead} />);
    await userEvent.click(screen.getByRole("button", { name: /^Papers/ }));
    const view = screen.getByRole("region", { name: /papers/i });
    const waiting = view.querySelector("[data-idle=Waiting]") as HTMLElement;
    // above the sources in use
    expect(waiting.compareDocumentPosition(view.querySelector("[data-health=links]")!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(within(waiting).getAllByRole("listitem")).toHaveLength(5);
    await userEvent.click(within(waiting).getByRole("button", { name: "Show all 7" }));
    expect(within(waiting).getAllByRole("listitem")).toHaveLength(7);
    await userEvent.click(within(waiting).getByRole("button", { name: "Show fewer" }));
    expect(within(waiting).getAllByRole("listitem")).toHaveLength(5);
  });

  it("a kind whose sources feed nothing says so", async () => {
    const lone = [src("m1", "mail", "listed")];
    render(<HealthLayer nodes={lone} neighbors={new Map()} byId={new Map(lone.map((n) => [n.id, n] as const))} support={new Map()} onRead={onRead} />);
    await userEvent.click(screen.getByRole("button", { name: /^Mail/ }));
    expect(screen.getByText("None of these sources feeds a concept yet.")).toBeInTheDocument();
  });

  it("leaving the Health view leaves the kind", async () => {
    const { unmount } = layer();
    await userEvent.click(screen.getByRole("button", { name: /^Papers/ }));
    unmount();
    expect(useHealth.getState().inside).toBeNull();
  });
});
