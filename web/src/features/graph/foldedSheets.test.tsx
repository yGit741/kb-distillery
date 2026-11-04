import { createMemoryHistory } from "@tanstack/react-router";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "@/app/providers";
import { createAppRouter } from "@/app/router";
import { mockDataSource } from "@/test/datasource";
import { sampleSnapshot } from "./fixtures";
import { useGraphUi } from "./store";

// jsdom has no canvas: stand in for force-graph with a chainable no-op instance (as GraphScreen.test.tsx does).
vi.mock("force-graph", () => {
  const make = () => {
    const proxy: unknown = new Proxy({}, { get: (_t, name: string) => (name === "_destructor" ? () => {} : () => proxy) });
    return proxy;
  };
  return { default: () => () => make() };
});

const ds = mockDataSource({ getGraph: async () => sampleSnapshot(), listScopes: async () => ({ scopes: [] }) as never });

beforeEach(() => useGraphUi.setState({ flyout: null }));

describe("Relations and Scopes folded into the graph", () => {
  it("?tool=scopes opens the Scopes sheet beside the canvas, and its own controls stay on /graph", async () => {
    const router = createAppRouter(createMemoryHistory({ initialEntries: ["/app/graph?tool=scopes"] }));
    render(<App source={ds} router={router} />);
    const sheet = await screen.findByRole("region", { name: "Scopes" });
    expect(sheet).toBeInTheDocument();
    expect(screen.getByTestId("graph-screen")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Close panel" }));
    expect(screen.queryByRole("region", { name: "Scopes" })).toBeNull();
    expect(router.state.location.pathname).toBe("/graph");
  });

  it("the toolbar has a Relation proposals tool that opens as a sheet", async () => {
    const router = createAppRouter(createMemoryHistory({ initialEntries: ["/app/graph"] }));
    render(<App source={ds} router={router} />);
    await userEvent.click(await screen.findByRole("button", { name: "Relation proposals" }));
    expect(await screen.findByRole("region", { name: "Relation proposals" })).toBeInTheDocument();
  });
});
