import { render, screen } from "@testing-library/react";
import { withFlag } from "@/flags/testing";
import { sampleNodes } from "./fixtures";
import { Legend } from "./Legend";
import type { GraphSchema } from "./schema";
import type { GNode } from "./types";

// flag graph.artifacts: an artifact view swaps in its own schema; the bottom legend keeps the artifact types as a group
const file = (id: string): GNode => ({ ...sampleNodes[0]!, id, title: id, type: "file", layer: "artifact" }) as GNode;

describe("bottom legend with an artifact layer", () => {
  it("lists the artifact types under their own layer label", () =>
    withFlag("graph.artifacts", true, () => {
      const nodes = [...sampleNodes, file("src/a.py"), file("src/b.py")];
      const schema: GraphSchema = {
        types: [{ id: "topic", label: "Topic", layer: "concept" }, { id: "file", label: "File", layer: "artifact" }],
        defaultVisible: ["topic", "file"],
        depths: [],
      } as GraphSchema;
      render(<Legend nodes={nodes} visible={new Set(nodes.map((n) => n.id))} schema={schema} shownTypes={null} stats="9 pages" />);
      expect(screen.getByText(/Artifacts:/)).toBeInTheDocument();
      expect(screen.getByText("File")).toBeInTheDocument();
    }));

  it("without artifact nodes there is no artifact group", () =>
    withFlag("graph.artifacts", false, () => {
      const schema: GraphSchema = { types: [{ id: "topic", label: "Topic", layer: "concept" }], defaultVisible: ["topic"], depths: [] } as GraphSchema;
      render(<Legend nodes={sampleNodes} visible={new Set(sampleNodes.map((n) => n.id))} schema={schema} shownTypes={null} stats="7 pages" />);
      expect(screen.queryByText(/Artifacts:/)).not.toBeInTheDocument();
    }));
});
