import { createMemoryHistory } from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "@/app/providers";
import { createAppRouter } from "@/app/router";
import type { DataSource, LifecycleSnapshot } from "@/api";
import { withFlag } from "@/flags/testing";
import { mockDataSource } from "@/test/datasource";
import { START_DISMISSED_KEY } from "./StartCard";

vi.mock("force-graph", () => {
  const make = () => {
    const proxy: unknown = new Proxy({}, { get: (_t, name: string) => (name === "_destructor" ? () => {} : () => proxy) });
    return proxy;
  };
  return { default: () => () => make() };
});

const snap = { version: "0.13.1", snapshots: [], working: undefined, infra_branches: undefined } as unknown as LifecycleSnapshot;
const emptyGraph = { nodes: [], links: [], concept_links: [], facets: { types: [], maturities: [], areas: [] } } as never;

function open(path: string, over: Partial<DataSource> = {}) {
  const router = createAppRouter(createMemoryHistory({ initialEntries: [path] }), "");
  render(
    <App
      source={mockDataSource({
        getLifecycle: async () => snap,
        getShareStatus: async () => ({ status: null, chip: null }),
        getGraphNodes: async () => [],
        getGraph: async () => emptyGraph,
        ...over,
      })}
      router={router}
    />,
  );
  return router;
}

const card = () => screen.queryByTestId("start-card");

describe("Start here card on Home", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it("screen.start on: Home opens with the card, carrying the Start guide", async () => {
    await withFlag("screen.start", true, async () => {
      open("/");
      expect(await screen.findByRole("heading", { name: "Start here", level: 2 })).toBeInTheDocument();
      expect(card()).toBeInTheDocument();
      expect(await screen.findByText("Edit knowledge")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Dismiss" })).toBeInTheDocument();
    });
  });

  it("screen.start off: no card, and no Start route", async () => {
    await withFlag("screen.start", false, async () => {
      open("/");
      await screen.findByText(/nothing to show yet/i);
      expect(card()).toBeNull();
      expect(screen.queryByText("Start here")).toBeNull();
    });
  });

  it("Dismiss hides the card and the choice is saved for the next visit", async () => {
    await withFlag("screen.start", true, async () => {
      const first = open("/");
      await userEvent.click(await screen.findByRole("button", { name: "Dismiss" }));
      expect(card()).toBeNull();
      expect(localStorage.getItem(START_DISMISSED_KEY)).toBe("1");
      expect(first.state.location.pathname).toBe("/");
    });
    document.body.innerHTML = "";
    await withFlag("screen.start", true, async () => {
      open("/");
      await screen.findByText(/nothing to show yet/i);
      expect(card()).toBeNull();
    });
  });

  it("/start redirects to /?start=true, which opens the card even when dismissed; Dismiss drops the param", async () => {
    localStorage.setItem(START_DISMISSED_KEY, "1");
    await withFlag("screen.start", true, async () => {
      const router = open("/start");
      expect(await screen.findByRole("heading", { name: "Start here", level: 2 })).toBeInTheDocument();
      expect(router.state.location.pathname).toBe("/");
      expect(router.state.location.search).toEqual({ start: true });
      expect(router.state.location.href).toMatch(/\?start=true$/); // a quoted "1" would read ?start=%221%22
      await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
      await waitFor(() => expect(card()).toBeNull());
      expect(router.state.location.search).toEqual({});
      expect(localStorage.getItem(START_DISMISSED_KEY)).toBe("1");
    });
  });

  it("/?start=1 forces the card open on a dismissed Home", async () => {
    localStorage.setItem(START_DISMISSED_KEY, "1");
    await withFlag("screen.start", true, async () => {
      open("/?start=1");
      expect(await screen.findByTestId("start-card")).toBeInTheDocument();
    });
  });

  it("screen.start off: /start lands on Home without a card (the route itself is dropped from builds with the flag off)", async () => {
    await withFlag("screen.start", false, async () => {
      open("/start");
      await screen.findByText(/nothing to show yet/i);
      expect(card()).toBeNull();
    });
  });

  it("storage that throws does not crash: the card shows, Dismiss still hides it for this visit", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("denied");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("denied");
    });
    await withFlag("screen.start", true, async () => {
      open("/");
      await userEvent.click(await screen.findByRole("button", { name: "Dismiss" }));
      expect(card()).toBeNull();
    });
  });
});
