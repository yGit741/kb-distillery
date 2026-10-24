import { createMemoryHistory, createRootRoute, createRouter, RouterProvider } from "@tanstack/react-router";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Tour } from "./Tour";
import { activeTour, markSeen, TOURS, type TourStep } from "./tours";

const demo: Record<string, readonly TourStep[]> = {
  demo: [
    { anchor: "one", title: "First", body: "the first thing" },
    { anchor: "missing", title: "Never shown", body: "" },
    { anchor: "two", title: "Second", body: "the second thing" },
  ],
};

function mount(ui: React.ReactNode) {
  const root = createRootRoute({
    component: () => (
      <>
        <div data-tour="one">one</div>
        <div data-tour="two">two</div>
        {ui}
      </>
    ),
  });
  const router = createRouter({ routeTree: root, history: createMemoryHistory({ initialEntries: ["/"] }) });
  return render(<RouterProvider router={router} />);
}

describe("tour", () => {
  beforeEach(() => localStorage.clear());

  it("ships no tour content yet", () => {
    expect(TOURS).toEqual({});
    expect(activeTour("kalai")).toEqual([]);
    expect(activeTour(null)).toEqual([]);
  });

  it("runs an unseen tour once", () => {
    expect(activeTour("demo", demo)).toHaveLength(3);
    markSeen("demo");
    expect(activeTour("demo", demo)).toEqual([]);
  });

  it("walks the steps, skips a missing anchor and remembers the finish", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mount(<Tour id="demo" tours={demo} />);
    await act(async () => void vi.advanceTimersByTime(200));
    expect(await screen.findByText("First")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await act(async () => void vi.advanceTimersByTime(2500));
    expect(await screen.findByText("Second")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(activeTour("demo", demo)).toEqual([]);
    vi.useRealTimers();
  });
});
