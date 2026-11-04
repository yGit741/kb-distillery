import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { DataSourceProvider, type DataSource } from "@/api";
import { mockDataSource } from "@/test/datasource";
import { useImportAdapter } from "./useImportAdapter";

const env = vi.hoisted(() => ({ profile: null as "public" | "private" | null }));
vi.mock("@/share/env", () => ({
  get SHARE_PROFILE() {
    return env.profile;
  },
}));

const access = (body: unknown, status = 200) => vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status })));

const render = (kind: DataSource["kind"], profile: "public" | "private" | null) => {
  env.profile = profile;
  const ds = { ...mockDataSource(), kind } as DataSource;
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={new QueryClient()}>
      <DataSourceProvider source={ds}>{children}</DataSourceProvider>
    </QueryClientProvider>
  );
  return renderHook(() => useImportAdapter(), { wrapper });
};

describe("useImportAdapter by build", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("the local app has an adapter", () => expect(render("http", null).result.current).not.toBeNull());
  it("the private share build has one for an owner whose inbox is set up", async () => {
    access({ owner: true, inbox: true });
    const { result } = render("embedded", "private");
    await waitFor(() => expect(result.current).not.toBeNull());
  });
  it.each([
    ["a non-owner", { owner: false, inbox: true }, 200],
    ["a site with no inbox bucket", { owner: true, inbox: false }, 200],
    ["a signed-out viewer", { error: "sign in first" }, 401],
  ])("the private share build has none for %s", async (_n, body, status) => {
    access(body, status);
    const { result } = render("embedded", "private");
    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/inbox/access", expect.anything()));
    await new Promise((r) => setTimeout(r, 30));
    expect(result.current).toBeNull();
  });
  it("a public snapshot has none and never asks the Worker", () => {
    access({ owner: true, inbox: true });
    expect(render("embedded", "public").result.current).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
  });
});
