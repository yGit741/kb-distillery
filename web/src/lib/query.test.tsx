import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DataSourceProvider, type DataSource } from "@/api";
import { useApiQuery } from "./useApiQuery";
import { createQueryClient, GRAPH_KEY, prefetchHeavy, QUERY_GC_MS, QUERY_STALE_MS } from "./query";

function Probe({ call }: { call: (ds: DataSource) => Promise<string> }) {
  const q = useApiQuery(["probe"], call);
  return <p>{q.data ?? "loading"}</p>;
}

describe("createQueryClient", () => {
  it("keeps data fresh for minutes, in memory for long, and never refetches on focus", () => {
    const o = createQueryClient().getDefaultOptions().queries!;
    expect(o.staleTime).toBe(QUERY_STALE_MS);
    expect(o.gcTime).toBe(QUERY_GC_MS);
    expect(o.refetchOnWindowFocus).toBe(false);
    expect(o.refetchOnMount).toBe(true);
    expect(QUERY_STALE_MS).toBeGreaterThanOrEqual(2 * 60_000);
  });

  it("does not call the fetcher again when a screen remounts on warm data", async () => {
    const client = createQueryClient();
    const fetcher = vi.fn(async () => "data");
    const ds = {} as DataSource;
    const ui = () => (
      <DataSourceProvider source={ds}>
        <QueryClientProvider client={client}>
          <Probe call={fetcher} />
        </QueryClientProvider>
      </DataSourceProvider>
    );
    const first = render(ui());
    expect(await screen.findByText("data")).toBeTruthy();
    first.unmount();
    render(ui());
    expect(screen.getByText("data")).toBeTruthy(); // at once, no spinner
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});

describe("prefetchHeavy", () => {
  it("warms the graph and pipeline on an http source, nothing on an embedded one", async () => {
    const getGraph = vi.fn(async () => ({ nodes: [], links: [] }));
    const getPipeline = vi.fn(async () => ({}));
    const client = createQueryClient();
    prefetchHeavy(client, { kind: "embedded", getGraph, getPipeline } as unknown as DataSource);
    expect(getGraph).not.toHaveBeenCalled();
    prefetchHeavy(client, { kind: "http", getGraph, getPipeline } as unknown as DataSource);
    await client.prefetchQuery({ queryKey: GRAPH_KEY, queryFn: getGraph }); // deduped with the in-flight prefetch
    expect(getGraph).toHaveBeenCalledTimes(1);
    expect(getPipeline).toHaveBeenCalledTimes(1);
    expect(client.getQueryData(GRAPH_KEY)).toBeTruthy();
  });
});
