import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DataSourceProvider } from "@/api";
import { mockDataSource } from "@/test/datasource";
import { SideReader } from "./SideReader";

function mount(step?: { index: number; total: number; go: (d: -1 | 1) => void }) {
  const ds = mockDataSource({ getPage: (async () => ({ card: { title: "A page", type: "idea" }, markdown: "Body" })) as never });
  return render(
    <DataSourceProvider source={ds}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <SideReader slug="a" title="A" pageHref="/pages/a" onClose={vi.fn()} step={step} />
      </QueryClientProvider>
    </DataSourceProvider>,
  );
}

describe("SideReader stepper", () => {
  it("shows N of M and moves with the buttons and with [ and ]", async () => {
    const go = vi.fn();
    mount({ index: 2, total: 3, go });
    expect(screen.getByText("2 of 3")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Next page" }));
    await userEvent.click(screen.getByRole("button", { name: "Previous page" }));
    fireEvent.keyDown(window, { key: "]" });
    fireEvent.keyDown(window, { key: "[" });
    expect(go.mock.calls).toEqual([[1], [-1], [1], [-1]]);
  });

  it("disables previous on the first page; no stepper for one page", () => {
    mount({ index: 1, total: 2, go: vi.fn() });
    expect(screen.getByRole("button", { name: "Previous page" })).toBeDisabled();
  });

  it("has no stepper without a set", () => {
    mount();
    expect(screen.queryByRole("navigation", { name: "Pages in this set" })).toBeNull();
  });
});
