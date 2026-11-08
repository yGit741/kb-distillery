import { createMemoryHistory } from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import { App } from "@/app/providers";
import { createAppRouter } from "@/app/router";
import type { KbInfo } from "@/api/types";
import { sampleSnapshot } from "@/features/graph/fixtures";
import { mockDataSource } from "@/test/datasource";

vi.mock("@/features/graph/GraphCanvas", async () => {
  const { forwardRef } = await import("react");
  return { GraphCanvas: forwardRef(() => <div data-testid="canvas" />) };
});

function open(readOnly: boolean) {
  const info = { id: "demo", name: "Demo", root: "/x/demo", read_only: readOnly } as unknown as KbInfo;
  const ds = mockDataSource({
    getKb: async () => info,
    getGraph: async () => sampleSnapshot(),
    getShareStatus: async () => ({ status: null, chip: null }),
    getGraphNodes: async () => [],
  });
  const router = createAppRouter(createMemoryHistory({ initialEntries: ["/graph"] }), "");
  render(<App source={ds} router={router} />);
}

describe("ReadOnlyBanner", () => {
  it("shows the notice and a Start link on a read-only kb", async () => {
    open(true);
    const banner = await screen.findByTestId("read-only-banner");
    expect(banner.textContent).toContain("Read-only example knowledge base. Create your own to add sources.");
    expect(banner.querySelector("a")?.getAttribute("href")).toBe("/start");
  });

  it("shows nothing on a writable kb", async () => {
    open(false);
    await screen.findByText("Demo");
    await waitFor(() => expect(screen.queryByTestId("read-only-banner")).toBeNull());
  });
});
