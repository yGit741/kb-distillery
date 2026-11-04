import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StartCard } from "./StartCard";

vi.mock("@/features/start/StartScreen", () => ({ StartScreen: () => <p>the guide</p> }));

beforeEach(() => localStorage.clear());

describe("StartCard", () => {
  it("opens the guide in place and stays gone once dismissed", async () => {
    const { unmount } = render(<StartCard />);
    expect(screen.queryByText("the guide")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: /Open guide/ }));
    expect(screen.getByText("the guide")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Dismiss the start card" }));
    expect(screen.queryByTestId("start-card")).toBeNull();
    unmount();
    render(<StartCard />);
    expect(screen.queryByTestId("start-card")).toBeNull();
  });

  it("the old /start link opens it expanded even after a dismissal", () => {
    localStorage.setItem("home.start-card.dismissed", "1");
    render(<StartCard open />);
    expect(screen.getByText("the guide")).toBeInTheDocument();
  });
});
