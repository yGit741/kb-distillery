import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render } from "@testing-library/react";
import { DataSourceProvider } from "@/api";
import { useHeaderFold } from "@/app/headerFold";
import { listTours, runTour } from "@/features/tour/tours";
import { withFlag } from "@/flags/testing";
import { mockDataSource } from "@/test/datasource";
import { sampleNodes, sampleSnapshot } from "../../fixtures";
import { parseSchema } from "../../schema";
import { DEFAULT_PREFS, useGraphUi } from "../../store";
import { Corners } from "./Corners";
import { resetCorners, useCorners } from "./cornersStore";
import { VIEWS_TOUR, viewsTourSteps } from "./viewsTour";

const schema = parseSchema(sampleSnapshot().schema);
const visible = new Set(sampleNodes.filter((n) => ["topic", "idea", "question"].includes(n.type)).map((n) => n.id));
const host = { go: vi.fn(), href: (to: string) => to, openPage: vi.fn() };
const fetchViews = vi.fn(async () => new Response(JSON.stringify({ views: [] }))) as unknown as typeof fetch;

/** `bar`: stand-ins for the app bar's theme switch and the graph's chevron, which live outside the corners */
function mount({ bar = false }: { bar?: boolean } = {}) {
  const source = mockDataSource({ listThink: async () => ({ capture_note: "inbox.md", notes: [] }) });
  return render(
    <DataSourceProvider source={source}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        {bar && (
          <header>
            <button type="button" aria-label="Switch to dark theme" />
            <button type="button" data-testid="header-fold-button" onClick={() => useHeaderFold.getState().toggle()} />
          </header>
        )}
        <div style={{ position: "relative", width: 1200, height: 800 }}>
          <Corners nodes={sampleNodes} visible={visible} schema={schema} shownTypes={new Set(schema.defaultVisible)} stats="3 of 7 pages" host={host} applyView={vi.fn()} showPicked={vi.fn()} fetchImpl={fetchViews} />
        </div>
      </QueryClientProvider>
    </DataSourceProvider>,
  );
}

const listed = () => listTours().find((t) => t.name === VIEWS_TOUR);
/** drawn outside the corners: the Health dial, the app bar's chevron and theme switch */
const OUTSIDE = new Set(['[aria-label="Sources by kind"]', '[data-testid="header-fold-button"]', 'header button[aria-label^="Switch to"]']);

beforeEach(() => {
  localStorage.clear();
  resetCorners();
  useGraphUi.setState({ ...DEFAULT_PREFS, story: "", shownTypes: undefined, predicate: null, shownDepths: null, hiddenKeys: new Set(), spotlight: null, view: null });
  useHeaderFold.setState({ folded: false });
});
afterEach(() => {
  document.querySelector<HTMLButtonElement>(".gt-dock .gt-skip")?.click();
  document.body.innerHTML = "";
});

describe("graph-views tour", () => {
  it("is in the Tours menu while the graph corners are drawn, and leaves with them", () =>
    withFlag("graph-corners", true, () => {
      const r = mount();
      expect(listed()?.summary).toMatch(/pin/);
      r.unmount();
      expect(listed()).toBeUndefined();
    }));

  it("flag graph-corners off: no such tour", () =>
    withFlag("graph-corners", false, () => {
      mount();
      expect(listed()).toBeUndefined();
    }));

  it("follows the build: the Health step only when Sources opens Health, the chevron only when the bar folds", () => {
    expect(viewsTourSteps({ health: true, fold: true }).map((s) => s.title)).toEqual([
      "The graph opens on Concepts",
      "Your views hang from the pin",
      "Both ends fade",
      "Sources opens Health",
      "One fold, everywhere",
      "The bar folds from one spot",
    ]);
    expect(viewsTourSteps({ health: false, fold: false }).map((s) => s.title)).toEqual([
      "The graph opens on Concepts",
      "Your views hang from the pin",
      "Both ends fade",
      "One fold, everywhere",
      "Light or dark",
    ]);
    // flag graph.artifacts: the loop is one card per layer, so the two loop steps say that
    expect(viewsTourSteps({ health: false, fold: false, piles: true }).map((s) => s.title)).toEqual([
      "The graph opens on Concepts",
      "Your views hang from the pin",
      "The wheel turns the loop",
      "One fold, everywhere",
      "Light or dark",
    ]);
    expect(viewsTourSteps({ health: false, fold: false, piles: true })[1]!.body).not.toMatch(/V1|placeholder/);
  });

  it("each step is one idea in two sentences at most, and every [n] has its mark", () => {
    for (const s of [...viewsTourSteps({ health: true, fold: true }), ...viewsTourSteps({ health: true, fold: true, piles: true })]) {
      expect(s.body.split(/(?<=[.!?])\s+(?=[A-Z])/).length).toBeLessThanOrEqual(2);
      expect(s.body).not.toMatch(/\p{Extended_Pictographic}/u);
      for (const [, n] of s.body.matchAll(/\[(\d)\]/g)) expect(s.marks?.[Number(n) - 1]).toBeDefined();
    }
  });

  it("each step opens what it lights: the legend, the loop with a live Sources card, the types card and its dot", () =>
    withFlag("graph-corners", true, async () => {
      mount();
      // the chevron step's own setup folds the bar: the full run below covers it
      for (const s of viewsTourSteps({ health: true, fold: false })) {
        await act(async () => void (await s.before?.()));
        const clicks = (s.do ?? []).flatMap((a) => ("click" in a ? [a.click] : []));
        for (const sel of [s.target, ...(s.marks ?? []).map((m) => m.target), ...clicks]) {
          if (!sel || OUTSIDE.has(sel)) continue;
          expect(document.querySelector(sel), sel).not.toBeNull();
        }
      }
      const sources = document.querySelector('[data-view="view:sources"]')!;
      expect(sources.closest("[data-pos]")).not.toHaveAttribute("inert");
    }));

  it("the Sources step picks Sources with the loop open, then folds the loop so the dial shows", () =>
    withFlag("graph-corners", true, async () => {
      mount();
      const step = viewsTourSteps({ health: true, fold: true }).find((s) => s.title === "Sources opens Health")!;
      await act(async () => void (await step.before?.()));
      expect(useCorners.getState().has("pins")).toBe(true);
      const clicks = (step.do ?? []).flatMap((a) => ("click" in a ? [a.click] : []));
      expect(clicks).toEqual(['[data-view="view:sources"]', 'button[aria-label="Pinned views"]']);
      for (const sel of clicks) act(() => document.querySelector<HTMLElement>(sel)!.click());
      expect(useCorners.getState().has("pins")).toBe(false);
    }));

  const next = async (title: string) => {
    await act(async () => document.querySelector<HTMLButtonElement>(".gt-dock .gt-next")!.click());
    await vi.waitFor(() => expect(document.querySelector(".gt-card h4")?.textContent).toBe(title), { timeout: 5000 });
  };

  it.each([
    ["open", false],
    ["folded", true],
  ])("played through with the bar %s: the chevron step shows the bar opening, and the end puts it back as it was", (_, before) =>
    withFlag("knowledge-health", false, () =>
      withFlag("header-fold", true, () =>
        withFlag("graph-shell", true, () =>
          withFlag("graph-corners", true, async () => {
            useHeaderFold.getState().set(before);
            mount({ bar: true });
            act(() => void runTour(VIEWS_TOUR));
            await vi.waitFor(() => expect(document.querySelector(".gt-card h4")?.textContent).toBe("The graph opens on Concepts"), { timeout: 5000 });
            await next("Your views hang from the pin");
            await next("Both ends fade");
            await next("One fold, everywhere");
            await next("The bar folds from one spot");
            // the press it acted out brought the bar back, whatever it was before
            expect(useHeaderFold.getState().folded).toBe(false);
            await act(async () => document.querySelector<HTMLButtonElement>(".gt-dock .gt-next")!.click());
            await vi.waitFor(() => expect(document.querySelector(".gt-dock")).toBeNull());
            expect(useHeaderFold.getState().folded).toBe(before);
            expect(localStorage.getItem("kb-header-folded")).toBe(before ? "1" : "0");
          })))), 20_000);
});
