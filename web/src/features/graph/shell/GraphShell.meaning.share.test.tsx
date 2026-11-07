import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataSourceProvider } from "@/api";
import { withFlag } from "@/flags/testing";
import { mockDataSource } from "@/test/datasource";
import { node } from "../fixtures";
import { GraphShell } from "./GraphShell";

vi.mock("@/share/env", () => ({ IS_SHARE: true, SHARE_PROFILE: "public" }));

const nodes = [node("margin-theory", { title: "Margin theory" }), node("kernel", { title: "Kernel methods" })];
const byId = new Map(nodes.map((n) => [n.id, n] as const));

it("the share build asks the meaning service nothing and offers no Ask row", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const ui = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
  const searchSimilar = vi.fn();
  const ds = mockDataSource({ search: async () => ({ hits: [], total: 0 }), listRecent: async () => ({ recent: [] }), listViews: async () => ({ views: [] }), searchSimilar });
  await withFlag("graph-intent", true, () =>
    withFlag("semantic-search", true, async () => {
      render(
        <DataSourceProvider source={ds}>
          <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
            <GraphShell nodes={nodes} links={[]} byId={byId} colorBy="type" shownTypes={new Set(nodes.map((n) => n.type))} onFocus={vi.fn()} onRead={vi.fn()} onShowExact={vi.fn()} onShowMentions={vi.fn()} onFit={vi.fn()} onZoom={vi.fn()} onReheat={vi.fn()} onRefresh={vi.fn()} />
          </QueryClientProvider>
        </DataSourceProvider>,
      );
      await ui.type(screen.getByRole("combobox", { name: /search the graph/i }), "margin");
      await act(() => vi.advanceTimersByTime(600));
      expect(await screen.findByRole("option", { name: /margin theory/i })).toBeInTheDocument();
      expect(searchSimilar).not.toHaveBeenCalled();
      expect(screen.queryByRole("group", { name: "Related by meaning" })).not.toBeInTheDocument();
      expect(screen.queryByRole("option", { name: /ask/i })).not.toBeInTheDocument();
    }),
  );
  vi.useRealTimers();
});
