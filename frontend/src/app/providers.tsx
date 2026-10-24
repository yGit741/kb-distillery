import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { useState } from "react";
import { DataSourceProvider, defaultDataSource, type DataSource } from "@/api";
import { createQueryClient } from "@/lib/query";
import { createAppRouter } from "./router";

export function App({ source, router }: { source?: DataSource; router?: ReturnType<typeof createAppRouter> }) {
  const [ds] = useState(() => source ?? defaultDataSource());
  const [client] = useState(() => createQueryClient());
  const [rt] = useState(() => router ?? createAppRouter());
  return (
    <DataSourceProvider source={ds}>
      <QueryClientProvider client={client}>
        <RouterProvider router={rt} />
      </QueryClientProvider>
    </DataSourceProvider>
  );
}
