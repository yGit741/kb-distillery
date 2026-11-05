import { createMemoryHistory } from "@tanstack/react-router";
import { render, screen } from "@testing-library/react";
import { App } from "./providers";
import { createAppRouter } from "./router";
import type { DataSource } from "@/api";
import { withFlag } from "@/flags/testing";
import { mockDataSource } from "@/test/datasource";

// a share or static build: the pinned panel has no Dark mode switch, so the header keeps its own
vi.mock("@/share/env", () => ({ IS_SHARE: true, SHARE_PROFILE: "public" }));

const ds: DataSource = mockDataSource({
  getHealth: () => new Promise(() => {}),
  getShareStatus: async () => ({ status: null, chip: null }),
  getGraphNodes: async () => [],
});

describe("AppShell theme switch in a share build", () => {
  it("keeps the header theme switch on the graph although views-panel and graph-shell are on", () =>
    withFlag("views-panel", true, () =>
      withFlag("graph-shell", true, async () => {
        const router = createAppRouter(createMemoryHistory({ initialEntries: ["/app/graph"] }));
        render(<App source={ds} router={router} />);
        await screen.findByRole("navigation", { name: "Main", hidden: true });
        expect(screen.queryAllByRole("button", { name: /switch to/i, hidden: true })).toHaveLength(1);
      }),
    ));
});
