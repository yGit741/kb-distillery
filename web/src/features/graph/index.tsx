import { useNavigate, useSearch } from "@tanstack/react-router";
import { useMemo } from "react";
import type { SearchById } from "@/routes/search";
import { GraphScreen, type GraphHost } from "./GraphScreen";

export const ported = true;

const base = (import.meta.env.BASE_URL as string).replace(/\/$/, "");

/** The graph screen: the router supplies the typed search params and navigation; everything else is in GraphScreen. */
export default function Graph() {
  const search = useSearch({ strict: false }) as SearchById["graph"];
  const navigate = useNavigate();
  const host = useMemo<GraphHost>(
    () => ({
      openPage: (slug, kb) => void navigate({ to: `/pages/${encodeURIComponent(slug)}` as "/", search: (kb ? { kb } : {}) as never }),
      pageHref: (slug, kb) => `${base}/pages/${encodeURIComponent(slug)}${kb ? `?kb=${encodeURIComponent(kb)}` : ""}`,
      go: (to, search) => void navigate({ to: to as "/", ...(search ? { search: search as never } : {}) }),
      href: (to, search) => {
        const qs = new URLSearchParams(search).toString();
        return `${base}${to}${qs ? `?${qs}` : ""}`;
      },
      clearParams: (keys) =>
        void navigate({
          to: ".",
          replace: true,
          search: ((prev: Record<string, unknown>) => Object.fromEntries(Object.entries(prev).filter(([k]) => !keys.includes(k)))) as never,
        }),
      setParams: (patch) =>
        void navigate({
          to: ".",
          replace: true,
          search: ((prev: Record<string, unknown>) =>
            Object.fromEntries(Object.entries({ ...prev, ...patch }).filter(([, v]) => v !== undefined && v !== ""))) as never,
        }),
    }),
    [navigate],
  );
  return <GraphScreen search={search} host={host} />;
}
