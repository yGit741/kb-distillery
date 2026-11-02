import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { flag, setFlagOverrides } from "./index";
import { loadFlagOverrides } from "./load";
import { withFlag } from "./testing";
import { useFlag } from "./useFlag";

afterEach(() => setFlagOverrides({}));

function Probe() {
  return <span data-testid="v">{useFlag("ui.system-flags-tab") ? "on" : "off"}</span>;
}

describe("useFlag()", () => {
  it("re-renders when overrides change", () => {
    render(<Probe />);
    expect(screen.getByTestId("v").textContent).toBe("off");
    act(() => setFlagOverrides({ "ui.system-flags-tab": true }));
    expect(screen.getByTestId("v").textContent).toBe("on");
    act(() => setFlagOverrides({}));
    expect(screen.getByTestId("v").textContent).toBe("off");
  });
});

describe("loadFlagOverrides()", () => {
  it("installs the overrides from GET /api/flags", async () => {
    const f = vi.fn(async () => Response.json({ env: "local", overrides: { "ui.system-flags-tab": true, "screen.share": true } }));
    expect(await loadFlagOverrides(f as unknown as typeof fetch)).toBe(true);
    expect(f).toHaveBeenCalledWith("/api/flags", expect.anything());
    expect(flag("ui.system-flags-tab")).toBe(true);
    expect(flag("screen.share")).toBe(false); // build flags ignore overrides
  });
  it("keeps built values when the server fails", async () => {
    const f = vi.fn(async () => new Response("no", { status: 500 }));
    expect(await loadFlagOverrides(f as unknown as typeof fetch)).toBe(false);
    expect(flag("ui.system-flags-tab")).toBe(false);
  });
});

/** Flag test matrix (kb_distillery.config.flags.coverage): the runtime flag on and off. */
describe("ui.system-flags-tab states", () => {
  it("on → useFlag is true", () =>
    withFlag("ui.system-flags-tab", true, () => {
      render(<Probe />);
      expect(screen.getByTestId("v").textContent).toBe("on");
    }));
  it("off → useFlag is false even with a server override", () => {
    setFlagOverrides({ "ui.system-flags-tab": true });
    withFlag("ui.system-flags-tab", false, () => {
      render(<Probe />);
      expect(screen.getByTestId("v").textContent).toBe("off");
    });
  });
});
