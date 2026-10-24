import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { useState } from "react";
import { DataSourceProvider, defaultDataSource, type DataSource } from "@/api";
import { createAppRouter } from "./router";

export function App({ source, router }: { source?: DataSource; router?: ReturnType<typeof createAppRouter> }) {
  const [ds] = useState(() => source ?? defaultDataSource());
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { staleTime: 15_000, retry: 1 } } }));
  const [rt] = useState(() => router ?? createAppRouter());
  return (
    <DataSourceProvider source={ds}>
      <QueryClientProvider client={client}>
        <RouterProvider router={rt} />
      </QueryClientProvider>
    </DataSourceProvider>
  );
}
