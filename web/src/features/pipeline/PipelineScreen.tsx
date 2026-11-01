import { useNavigate, useSearch } from "@tanstack/react-router";
import { useCallback } from "react";
import type { SearchById } from "@/routes/search";
import { PipelineView, type SearchPatch } from "./PipelineView";

/** Route glue: filters, view and the open item live in the URL (src/routes/search.ts). */
export function PipelineScreen() {
  const search = useSearch({ strict: false }) as SearchById["pipeline"];
  const navigate = useNavigate();
  const onSearch = useCallback(
    (patch: SearchPatch) => {
      void navigate({
        to: ".",
        replace: true,
        search: ((prev: Record<string, unknown>) =>
          Object.fromEntries(Object.entries({ ...prev, ...patch }).filter(([, v]) => v !== undefined))) as never,
      });
    },
    [navigate],
  );
  return <PipelineView search={search} onSearch={onSearch} />;
}
