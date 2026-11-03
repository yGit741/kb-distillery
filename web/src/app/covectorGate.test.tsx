import { createMemoryHistory } from "@tanstack/react-router";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "./providers";
import { createAppRouter } from "./router";
import { setFlagOverrides } from "@/flags";
import { mockDataSource } from "@/test/datasource";

const ds = mockDataSource({
  getLifecycle: () => new Promise(() => {}),
  getOps: () => new Promise(() => {}),
  getHealth: () => new Promise(() => {}),
  getShareStatus: async () => ({ status: null, chip: null }),
  getGraphNodes: async () => [],
});

beforeEach(() => void vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null)); // jsdom has no canvas
afterEach(() => {
  vi.restoreAllMocks();
  act(() => setFlagOverrides({}));
});

describe("/covector is the owner's own page (research-tools)", () => {
  it("is Not Found and absent from the palette while the flag is off, and appears when it turns on", async () => {
    const router = createAppRouter(createMemoryHistory({ initialEntries: ["/covector"] }), "");
    render(<App source={ds} router={router} />);
    expect(await screen.findByText("Not Found")).toBeInTheDocument();
    expect(screen.queryByText("Covector Visualization")).not.toBeInTheDocument();

    await userEvent.keyboard("{Control>}k{/Control}");
    await screen.findByPlaceholderText(/^Go to…/);
    expect(screen.queryByText("Interactive picture of a covector acting on a vector.")).not.toBeInTheDocument();

    act(() => setFlagOverrides({ "research-tools": true }));
    expect(await screen.findByText("Interactive picture of a covector acting on a vector.")).toBeInTheDocument();
    expect(screen.queryByText("Not Found")).not.toBeInTheDocument();
  });
});
