import { render } from "@testing-library/react";
import { vi } from "vitest";
import { ScreenLink } from "./content";

// A share build's screen list (modules.share-private.ts): Start is there, Pipeline is not.
vi.mock("@/routes/modules", () => ({
  modules: { "../features/home/index.tsx": {}, "../features/start/index.tsx": {} },
}));

describe("ScreenLink in a build without the Pipeline screen", () => {
  it("renders the name as plain text for a real route whose screen was not imported", () => {
    const { container } = render(<ScreenLink id="pipeline">Digestion</ScreenLink>);
    expect(container).toHaveTextContent("Digestion");
    expect(container.querySelector("a")).toBeNull();
  });
});
