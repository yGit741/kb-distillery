import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, vi } from "vitest";
import { CovectorScreen } from "./CovectorScreen";

type Call = [string, ...unknown[]];

function stubCanvas() {
  const calls: Call[] = [];
  const ctx = new Proxy({} as Record<string, unknown>, {
    get: (t, k: string) => (k in t ? t[k] : (...a: unknown[]) => void calls.push([k, ...a])),
    set: (t, k: string, v) => ((t[k] = v), true),
  });
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(ctx as never);
  return calls;
}

afterEach(() => vi.restoreAllMocks());

describe("Covector screen", () => {
  it("starts with v = (3, 4), u = (2, 1) and the page's readouts", () => {
    stubCanvas();
    render(<CovectorScreen />);
    expect(screen.getByTestId("vx-val")).toHaveTextContent("3.0");
    expect(screen.getByTestId("vy-val")).toHaveTextContent("4.0");
    expect(screen.getByTestId("ux-val")).toHaveTextContent("2.0");
    expect(screen.getByTestId("uy-val")).toHaveTextContent("1.0");
    expect(screen.getByTestId("v-len")).toHaveTextContent("5.00");
    expect(screen.getByTestId("spacing")).toHaveTextContent("0.20");
    expect(screen.getByTestId("score")).toHaveTextContent("10.00");
  });

  it("the four sliders run -5…5 in steps of 0.1", () => {
    stubCanvas();
    render(<CovectorScreen />);
    for (const name of [/v_x/, /v_y/, /u_x/, /u_y/]) {
      const s = screen.getByLabelText(name);
      expect(s).toHaveAttribute("min", "-5");
      expect(s).toHaveAttribute("max", "5");
      expect(s).toHaveAttribute("step", "0.1");
    }
  });

  it("moving a slider updates the readouts and redraws", () => {
    const calls = stubCanvas();
    render(<CovectorScreen />);
    const before = calls.length;
    fireEvent.change(screen.getByLabelText(/v_x/), { target: { value: "-1" } });
    fireEvent.change(screen.getByLabelText(/v_y/), { target: { value: "0" } });
    expect(screen.getByTestId("v-len")).toHaveTextContent("1.00");
    expect(screen.getByTestId("spacing")).toHaveTextContent("1.00");
    expect(screen.getByTestId("score")).toHaveTextContent("-2.00");
    expect(calls.length).toBeGreaterThan(before);
  });

  it("a zero generator shows an infinite spacing", () => {
    stubCanvas();
    render(<CovectorScreen />);
    fireEvent.change(screen.getByLabelText(/v_x/), { target: { value: "0" } });
    fireEvent.change(screen.getByLabelText(/v_y/), { target: { value: "0" } });
    expect(screen.getByTestId("spacing")).toHaveTextContent("∞");
  });

  it("draws the axes, 81 level lines and both arrows", () => {
    const calls = stubCanvas();
    render(<CovectorScreen />);
    // 1 axes path + 81 level lines + 2 arrows = 84 strokes, plus one filled dot at the tip of u
    expect(calls.filter(([n]) => n === "stroke")).toHaveLength(84);
    expect(calls.filter(([n]) => n === "fill")).toHaveLength(1);
  });
});
