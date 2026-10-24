import { useQuery, type QueryKey, type UseQueryOptions } from "@tanstack/react-query";
import { useDataSource, type DataSource } from "@/api";

/** `useQuery` that hands the call the DataSource: `useApiQuery(["page", slug], (ds) => ds.getPage(slug))`. */
export function useApiQuery<T>(
  key: QueryKey,
  call: (ds: DataSource) => Promise<T>,
  options?: Omit<UseQueryOptions<T>, "queryKey" | "queryFn">,
) {
  const ds = useDataSource();
  return useQuery<T>({ queryKey: key, queryFn: () => call(ds), ...options });
}
