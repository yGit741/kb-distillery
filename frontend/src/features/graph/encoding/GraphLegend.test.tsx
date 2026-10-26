import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { node, sampleNodes } from "../fixtures";
import { assignAreaColors } from "../style";
import { colorChannel, fixedChannel, sizeChannel } from "./channels";
import { GraphLegend, glyphRows, typeRows } from "./GraphLegend";
import { ShapeIcon } from "./NodeMarkSvg";
import { GEOMETRY } from "./spec";

const row = (name: string) => document.querySelector(`[data-row="${name}"]`) as HTMLElement | null;

describe("GraphLegend", () => {
  it("lists only the marks and source glyphs present, concepts first", () => {
    expect(typeRows(sampleNodes).map((t) => t.label)).toEqual(["Topic", "Idea", "Question", "Person", "Collection", "Source"]);
    expect(typeRows([node("a", { type: "idea" })]).map((t) => t.label)).toEqual(["Idea"]);
    const g = glyphRows([node("p", { type: "paper", layer: "source" }), node("c", { type: "ai-chat", layer: "source" }), node("i", { type: "idea" })]);
    expect(g.map((r) => r.label)).toEqual(["Paper", "AI chat"]);
  });

  it("always titles the colour row with the surface's channel", () => {
    assignAreaColors(sampleNodes);
    render(<GraphLegend nodes={sampleNodes} color={colorChannel("area")} size={sizeChannel("logdeg")} />);
    expect(within(row("colour")!).getByText("Colour = theme")).toBeInTheDocument();
    expect(within(row("colour")!).getByText("Learning theory")).toBeInTheDocument();
    expect(within(row("size")!).getByText("Size = links")).toBeInTheDocument();
    expect(within(row("type")!).getByText("Question")).toBeInTheDocument();
    expect(within(row("sources")!).getByText("Paper")).toBeInTheDocument();
  });

  it("drops the Size row when every node is one size, and the Sources row without sources", () => {
    render(<GraphLegend nodes={[node("a", { type: "idea" })]} color={colorChannel("area")} size={sizeChannel("uniform")} density="compact" />);
    expect(row("size")).toBeNull();
    expect(row("sources")).toBeNull();
    expect(screen.getByRole("group", { name: "Legend" })).toHaveAttribute("data-density", "compact");
  });

  it("titles a channel of the surface's own (citation role) and counts its values", () => {
    const role = fixedChannel("role", "citation role", (n) => (n.id === "a" ? "focus" : "cited"), [
      { key: "focus", label: "this paper", color: "#000" },
      { key: "cited", label: "it cites", color: "#111" },
      { key: "citing", label: "cites it", color: "#222" },
    ]);
    const nodes = [node("a", { type: "paper", layer: "source" }), node("b", { type: "paper", layer: "source" })];
    expect(role.rows(nodes)).toEqual([
      { label: "this paper", color: "#000", count: 1 },
      { label: "it cites", color: "#111", count: 1 },
    ]);
    render(<GraphLegend nodes={nodes} color={role} density="compact" />);
    expect(screen.getByText("Colour = citation role")).toBeInTheDocument();
  });

  it("folds colour values past the compact limit into +N", () => {
    const many = Array.from({ length: 6 }, (_, i) => node(`n${i}`, { type: "idea", status: `s${i}` }));
    render(<GraphLegend nodes={many} color={colorChannel("status")} density="compact" maxColors={4} />);
    expect(screen.getByText("+2")).toBeInTheDocument();
  });
});

describe("GraphLegend ramp", () => {
  it("shows an ordered colouring whole, between its two ends", () => {
    const nodes = ["listed", "easy", "full", "deep"].map((d, i) => node(`s${i}`, { type: "paper", layer: "source", depth: d }));
    render(<GraphLegend nodes={nodes} color={colorChannel("depth", { ramp: "light" })} density="compact" maxColors={2} />);
    const r = row("colour")!;
    expect(within(r).getByText("Colour = depth")).toBeInTheDocument();
    expect(within(r).getByText("listed")).toBeInTheDocument();
    expect(within(r).getByText("deep")).toBeInTheDocument();
    expect(within(r).queryByText(/^\+/)).toBeNull();
    expect(r.querySelectorAll("i")).toHaveLength(4);
  });
});

describe("ShapeIcon", () => {
  it("draws the canvas geometry (fractions of r)", () => {
    const { container } = render(<ShapeIcon shape="idea" />);
    const [ring, dot] = [...container.querySelectorAll("circle")].map((c) => Number(c.getAttribute("r")));
    expect(dot! / ring!).toBeCloseTo(GEOMETRY.ideaDot);
    const { container: c2 } = render(<ShapeIcon shape="collection" />);
    const [outer, inner] = [...c2.querySelectorAll("circle")].map((c) => Number(c.getAttribute("r")));
    expect(outer! / inner!).toBeCloseTo(GEOMETRY.collectionOuter);
  });
});
