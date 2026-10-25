import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { DataSourceProvider, defaultDataSource, type DataSource } from "@/api";
import { createQueryClient } from "@/lib/query";
import { createAppRouter } from "./router";

export function App({ source, router }: { source?: DataSource; router?: ReturnType<typeof createAppRouter> }) {
  const [ds] = useState(() => source ?? defaultDataSource());
  const [client] = useState(() => createQueryClient());
  const [rt] = useState(() => router ?? createAppRouter());
  // guided tours (features/tour) move between screens through this hook: `/graph?view=thesis` → navigate
  useEffect(() => {
    window.kbGo = (path) => {
      const [to = "/", qs = ""] = path.split("?");
      void rt.navigate({ to: to as "/", search: Object.fromEntries(new URLSearchParams(qs)) as never });
    };
    return () => {
      delete window.kbGo;
    };
  }, [rt]);
  return (
    <DataSourceProvider source={ds}>
      <QueryClientProvider client={client}>
        <RouterProvider router={rt} />
      </QueryClientProvider>
    </DataSourceProvider>
  );
}
