import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataSourceProvider } from "@/api";
import { runTour } from "@/features/tour/tours";
import { mockDataSource } from "@/test/datasource";
import { sampleNodes } from "../../fixtures";
import { GraphShell } from "../GraphShell";
import { registerShellTour, SHELL_TOUR } from "./shellTour";

const byId = new Map(sampleNodes.map((n) => [n.id, n] as const));
const title = () => document.querySelector(".gt-card h4")?.textContent;
const next = () => document.querySelector<HTMLButtonElement>(".gt-dock .gt-next")!;

afterEach(() => {
  document.querySelector<HTMLButtonElement>(".gt-dock .gt-skip")?.click();
});

/** The tour against the real search line and panel, not stand-ins: its selectors exist, and a typing step is safe. */
describe("shell tour on the real search line", () => {
  it("points at elements the shell really has, and Enter on a typing step moves the tour on without running a command", async () => {
    const onFit = vi.fn();
    const source = mockDataSource({ search: async () => ({ hits: [], total: 0 }), listRecent: async () => ({ recent: [] }), listViews: async () => ({ views: [] }), addRecent: vi.fn(async () => ({ recent: [] })) });
    render(
      <DataSourceProvider source={source}>
        <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
          <GraphShell nodes={sampleNodes} byId={byId} colorBy="type" onFocus={vi.fn()} onRead={vi.fn()} onShowMentions={vi.fn()} onFit={onFit} onZoom={vi.fn()} onReheat={vi.fn()} onRefresh={vi.fn()} />
        </QueryClientProvider>
      </DataSourceProvider>,
    );
    expect(document.querySelector('[data-testid="graph-shell"]')).not.toBeNull();
    const input = document.querySelector<HTMLInputElement>('[data-tour="graph-search"]')!;
    expect(input).not.toBeNull();

    registerShellTour();
    expect(runTour(SHELL_TOUR)).toBe(true);
    await waitFor(() => expect(title()).toBe("One line for everything"), { timeout: 4000 });
    next().click();
    await waitFor(() => expect(title()).toBe("Find a page"), { timeout: 4000 });
    next().click();
    // step 3 types "/" into the line: the panel opens and stays open, and focus stays in the line
    await waitFor(() => expect(title()).toBe("Commands start with a slash"), { timeout: 8000 });
    expect(input.value).toBe("/");
    expect(document.getElementById("graph-shell-list")).not.toBeNull();
    expect(input).toHaveFocus();
    await userEvent.keyboard("{Enter}");
    expect(onFit).not.toHaveBeenCalled();
    await waitFor(() => expect(title()).toBe("Anything else is a question"), { timeout: 8000 });
    // leaving the tour leaves the line empty
    document.querySelector<HTMLButtonElement>(".gt-dock .gt-skip")!.click();
    expect(input.value).toBe("");
    expect(screen.queryByRole("dialog", { name: "Guided tour" })).toBeNull();
  }, 40_000);
});
