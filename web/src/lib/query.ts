import { QueryClient } from "@tanstack/react-query";
import { ApiError } from "@/api";

/** Server state defaults: fresh for 15 s, one retry for network/5xx, none for a definite 4xx answer. */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 15_000,
        refetchOnWindowFocus: false,
        retry: (count, err) => count < 1 && !(err instanceof ApiError && err.status !== undefined && err.status < 500),
      },
    },
  });
}
