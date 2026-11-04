import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { DataSourceProvider, type ShareStatus } from "@/api";
import { mockDataSource } from "@/test/datasource";
import { ShareChip } from "./ShareChip";

function show(chip: { label: string; cls: string; href: string; title: string }) {
  const ds = mockDataSource({ getShareStatus: async () => ({ status: null, chip }) as unknown as ShareStatus });
  render(
    <QueryClientProvider client={new QueryClient()}>
      <DataSourceProvider source={ds}>
        <ShareChip />
      </DataSourceProvider>
    </QueryClientProvider>,
  );
  return screen.findByTestId("share-chip");
}

describe("ShareChip", () => {
  it("link carries the 24px target-size class", async () => {
    const el = await show({ label: "kb-1.0.0 · 2 h ago", cls: "ok", href: "https://example.com", title: "t" });
    expect(el.tagName).toBe("A");
    expect(el.className).toContain("min-h-6");
    expect(el.className).toContain("items-center");
  });

  it("status twin without a destination keeps the same height", async () => {
    const el = await show({ label: "kb-1.0.0 · 2 h ago", cls: "ok", href: "", title: "t" });
    expect(el.getAttribute("role")).toBe("status");
    expect(el.className).toContain("min-h-6");
  });
});
