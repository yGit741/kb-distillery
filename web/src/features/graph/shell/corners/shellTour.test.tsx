import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import { DataSourceProvider } from "@/api";
import { listTours, markSeen, seenTour } from "@/features/tour/tours";
import { withFlag } from "@/flags/testing";
import { mockDataSource } from "@/test/datasource";
import { sampleNodes, sampleSnapshot } from "../../fixtures";
import { parseSchema } from "../../schema";
import { DEFAULT_PREFS, useGraphUi } from "../../store";
import { Corners } from "./Corners";
import { resetCorners } from "./cornersStore";
import { clearSearchLine, SHELL_TOUR, shellTourAuto, shellTourSteps } from "./shellTour";

const schema = parseSchema(sampleSnapshot().schema);
const visible = new Set(sampleNodes.filter((n) => ["topic", "idea", "question"].includes(n.type)).map((n) => n.id));
const host = { go: vi.fn(), href: (to: string) => to, openPage: vi.fn() };
const dock = () => document.querySelector(".gt-dock");

function mount(kind: "http" | "embedded" = "http") {
  const source = mockDataSource({ kind, listThink: async () => ({ capture_note: "inbox.md", notes: [] }) });
  return render(
    <DataSourceProvider source={source}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <div style={{ position: "relative", width: 1200, height: 800 }}>
          <div data-testid="graph-shell">
            <input data-tour="graph-search" aria-label="search" />
          </div>
          <Corners nodes={sampleNodes} visible={visible} schema={schema} shownTypes={new Set(schema.defaultVisible)} stats="3 of 7 pages" host={host} applyView={vi.fn()} showPicked={vi.fn()} fetchImpl={vi.fn() as unknown as typeof fetch} />
        </div>
      </QueryClientProvider>
    </DataSourceProvider>,
  );
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  localStorage.clear();
  resetCorners();
  useGraphUi.setState({ ...DEFAULT_PREFS, shownTypes: undefined, predicate: null, shownDepths: null, hiddenKeys: new Set(), spotlight: null, view: null });
  window.history.replaceState(null, "", "/");
  shellTourAuto.enabled = true;
});
afterEach(() => {
  document.querySelector<HTMLButtonElement>(".gt-dock .gt-skip")?.click();
  document.body.innerHTML = "";
  shellTourAuto.enabled = import.meta.env.MODE !== "test";
  vi.useRealTimers();
});

describe("shell tour steps", () => {
  const all = () => true;
  it("walks the search line, then each corner that exists, then the page types", () => {
    const titles = shellTourSteps(all, false).map((s) => s.title);
    expect(titles).toEqual(["One line for everything", "Find a page", "Commands start with a slash", "Anything else is a question", "Describe how it should look", "Pinned views", "Think notes", "Agent chats", "Page types"]);
  });

  it("every step names a real selector, one idea, two sentences at most, and no emoji", () => {
    for (const s of shellTourSteps(all, false)) {
      expect(s.target).toMatch(/^(\[data-(tour|testid)="[a-z-]+"\]|#graph-shell-list)$/);
      expect(s.body.split(/(?<=[.!?])\s+(?=[A-Z])/).length).toBeLessThanOrEqual(2);
      expect(`${s.title}${s.body}`).toMatch(/^[\x20-\x7e]*$/);
    }
    expect(shellTourSteps(all, false)[0]!.go).toBe("/graph");
  });

  it("leaves out what a snapshot does not have: no chat step, no corners that are not drawn", () => {
    const titles = shellTourSteps((sel) => sel.includes("graph-types"), true).map((s) => s.title);
    expect(titles).toEqual(["One line for everything", "Find a page", "Commands start with a slash", "Describe how it should look", "Page types"]);
  });

  it("clearSearchLine empties the line and lets go of focus", () => {
    document.body.innerHTML = '<input data-tour="graph-search" value="/" />';
    const input = document.querySelector("input")!;
    const seen = vi.fn();
    input.addEventListener("input", seen);
    input.focus();
    clearSearchLine();
    expect(input.value).toBe("");
    expect(seen).toHaveBeenCalled();
    expect(document.activeElement).not.toBe(input);
  });
});

describe("shell tour on the graph screen", () => {
  it("flag on: registered while the corners are up, offered once, remembered when skipped", () =>
    withFlag("graph-shell", true, async () => {
      const { unmount } = mount();
      expect(listTours().map((t) => t.name)).toContain(SHELL_TOUR);
      expect(dock()).toBeNull();
      await act(async () => {
        vi.advanceTimersByTime(shellTourAuto.delayMs + 50);
      });
      expect(dock()).not.toBeNull();
      expect(document.body).toHaveClass("gt-active");
      expect(await screen.findByRole("heading", { name: "One line for everything" })).toBeInTheDocument();
      await act(async () => {
        document.querySelector<HTMLButtonElement>(".gt-skip")!.click();
      });
      expect(dock()).toBeNull();
      expect(seenTour(SHELL_TOUR)).toBe(true);
      unmount();
      expect(listTours({ all: true }).map((t) => t.name)).not.toContain(SHELL_TOUR);
      // the next visit stays quiet
      mount();
      await act(async () => {
        vi.advanceTimersByTime(shellTourAuto.delayMs + 50);
      });
      expect(dock()).toBeNull();
    }), 20_000);

  it("flag on: the corners carry the marks the steps point at", () =>
    withFlag("graph-shell", true, () => {
      mount();
      for (const t of ["graph-views", "graph-think", "graph-agent", "graph-types"]) expect(document.querySelector(`[data-tour="${t}"]`), t).not.toBeNull();
    }));

  it("flag on: a seen tour, an embed or a link that names a tour does not start by itself", () =>
    withFlag("graph-shell", true, async () => {
      markSeen(SHELL_TOUR);
      mount();
      await act(async () => {
        vi.advanceTimersByTime(shellTourAuto.delayMs + 50);
      });
      expect(dock()).toBeNull();
      document.body.innerHTML = "";
      localStorage.clear();
      window.history.replaceState(null, "", "/?tour=other");
      mount();
      await act(async () => {
        vi.advanceTimersByTime(shellTourAuto.delayMs + 50);
      });
      expect(dock()).toBeNull();
      document.body.innerHTML = "";
      window.history.replaceState(null, "", "/?embed=1");
      mount();
      await act(async () => {
        vi.advanceTimersByTime(shellTourAuto.delayMs + 50);
      });
      expect(dock()).toBeNull();
    }));

  it("flag off: nothing is registered and nothing starts", () =>
    withFlag("graph-shell", false, async () => {
      mount();
      expect(listTours({ all: true }).map((t) => t.name)).not.toContain(SHELL_TOUR);
      await act(async () => {
        vi.advanceTimersByTime(shellTourAuto.delayMs + 50);
      });
      expect(dock()).toBeNull();
      expect(seenTour(SHELL_TOUR)).toBe(false);
    }));
});
