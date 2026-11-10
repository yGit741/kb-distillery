import { createMemoryHistory } from "@tanstack/react-router";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "@/app/providers";
import { createAppRouter } from "@/app/router";
import type { DataSource } from "@/api";
import { resetAllVariants, savedVariant, useVariant, VARIANTS } from "@/components/variants";
import { withFlag } from "@/flags/testing";
import { summaryFixture } from "@/features/proposals/fixtures";
import { mockDataSource } from "@/test/datasource";
import { tryTargets } from "@/features/proposals/model";

const base: Partial<DataSource> = {
  getLifecycle: async () => ({ version: "1.0.0", working: { lanes: {} }, timeline: [] }) as never,
  getOps: async () => ({ doc: {}, threads: [], hygiene: { errors: 0, warnings: 0, findings: [] }, runs: [], nightly: {} }) as never,
  getHealth: async () => ({ inbox_count: 0, values: {}, statuses: {}, orphan_slugs: [] }) as never,
  getShareStatus: async () => ({ status: null, chip: null }),
  getGraphNodes: async () => [],
  listProposals: async () => [summaryFixture({ id: "p9", pages: ["tensor-rank", "matrix-rank"] }), summaryFixture({ id: "p8", pages: ["tensor-rank"] })],
};

function open(path = "/system?tab=variants") {
  const router = createAppRouter(createMemoryHistory({ initialEntries: [path] }), "");
  render(<App source={mockDataSource(base)} router={router} />);
  return router;
}

afterEach(() => {
  resetAllVariants();
  localStorage.clear();
});

describe("Variants tab", () => {
  it("lists every registry component with all its options and marks the default", async () => {
    await withFlag("ui.variant-chooser", true, async () => {
      open();
      for (const [id, spec] of Object.entries(VARIANTS)) {
        const group = await screen.findByRole("radiogroup", { name: spec.label });
        const radios = within(group).getAllByRole("radio");
        expect(radios.map((r) => r.textContent)).toEqual(spec.options.map((o) => expect.stringContaining(o.label)));
        const checked = radios.find((r) => r.getAttribute("aria-checked") === "true");
        expect(checked?.textContent).toContain("default");
        expect(screen.getByText(id)).toBeInTheDocument();
      }
    });
  });

  it("a pick writes the key the screens read, and reset clears it", async () => {
    await withFlag("ui.variant-chooser", true, async () => {
      open();
      const group = await screen.findByRole("radiogroup", { name: VARIANTS["page-sources"]!.label });
      await userEvent.click(within(group).getByRole("radio", { name: /Side tab/ }));
      expect(localStorage.getItem("kbd.variants.page-sources")).toBe("side-tab");
      expect(within(group).getByRole("radio", { name: /Side tab/ })).toHaveAttribute("aria-checked", "true");
      await userEvent.click(screen.getByRole("button", { name: "Reset to defaults" }));
      expect(localStorage.getItem("kbd.variants.page-sources")).toBeNull();
      expect(savedVariant("page-sources")).toBeNull();
      expect(within(group).getByRole("radio", { name: /Footer/ })).toHaveAttribute("aria-checked", "true");
    });
  });

  it("copy gives one plain line per component", async () => {
    const writeText = vi.fn(async (_t: string) => {});
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    await withFlag("ui.variant-chooser", true, async () => {
      open();
      const group = await screen.findByRole("radiogroup", { name: VARIANTS["proposal-diff"]!.label });
      await userEvent.click(within(group).getByRole("radio", { name: /Reading/ }));
      await userEvent.click(screen.getByRole("button", { name: "Copy choices" }));
      const text = String(writeText.mock.calls[0]?.[0]);
      expect(text.split("\n")).toHaveLength(Object.keys(VARIANTS).length);
      expect(text).toContain("proposal-diff: reading (default inline)");
      expect(text).toContain("page-sources: footer (default)");
    });
  });

  it("try it opens the page most open proposals touch", async () => {
    await withFlag("ui.variant-chooser", true, async () => {
      open();
      const sec = await screen.findByRole("region", { name: VARIANTS["page-sources"]!.label });
      await waitFor(() => expect(within(sec).getByRole("link", { name: "Try it" })).toHaveAttribute("href", "/pages/tensor-rank"));
      const diff = screen.getByRole("region", { name: VARIANTS["proposal-diff"]!.label });
      expect(within(diff).getByRole("link", { name: "Try it" })).toHaveAttribute("href", "/proposals/p9");
    });
  });

  it("is not offered while the flag is off", async () => {
    await withFlag("ui.variant-chooser", false, async () => {
      open();
      await screen.findByRole("tablist", { name: "System sections" });
      expect(screen.queryByRole("tab", { name: "Variants" })).toBeNull();
      expect(screen.queryByRole("radiogroup")).toBeNull();
    });
  });
});

describe("variants store", () => {
  it("a screen using useVariant follows a reset without reload", async () => {
    function Probe() {
      const [v] = useVariant("page-sources", ["footer", "side-tab", "hover-marks"], "footer");
      return <span data-testid="v">{v}</span>;
    }
    localStorage.setItem("kbd.variants.page-sources", "hover-marks");
    render(<Probe />);
    expect(screen.getByTestId("v")).toHaveTextContent("hover-marks");
    act(() => resetAllVariants());
    await waitFor(() => expect(screen.getByTestId("v")).toHaveTextContent("footer"));
  });

  it("tryTargets picks the most-touched page and the newest proposal", () => {
    expect(tryTargets([])).toEqual({ page: undefined, proposal: undefined });
    expect(tryTargets([{ id: "a", pages: ["x", "y"] }, { id: "b", pages: ["y"] }])).toEqual({ page: "y", proposal: "a" });
  });
});
