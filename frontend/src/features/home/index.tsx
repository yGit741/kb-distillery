import { useNavigate, useSearch } from "@tanstack/react-router";
import type { SearchById } from "@/routes/search";
import { useMemo } from "react";
import { withDefaultView } from "@/features/graph/defaultView";
import { HomeScreen, type HomeHost } from "./HomeScreen";

export const ported = true;

const base = (import.meta.env.BASE_URL as string).replace(/\/$/, "");

/** Home: the router supplies navigation to the full graph; everything else is in HomeScreen. */
export default function Home() {
  const navigate = useNavigate();
  const host = useMemo<HomeHost>(
    () => ({
      // `from=home` gives the graph a way back; a snapshot's default view (`--view`) rides along as `view`
      openGraph: (search) => void navigate({ to: "/graph" as "/", search: { ...withDefaultView(search), from: "home" } as never }),
      graphHref: (search) => `${base}/graph?${new URLSearchParams({ ...withDefaultView(search), from: "home" }).toString()}`,
      openPage: (slug) => void navigate({ to: `/pages/${encodeURIComponent(slug)}` as "/" }),
      pageHref: (slug) => `${base}/pages/${encodeURIComponent(slug)}`,
      // replace + resetScroll:false: picking a concept must keep the page where it is
      setConcept: (slug) => void navigate({ to: "/", search: { concept: slug } as never, replace: true, resetScroll: false }),
    }),
    [navigate],
  );
  const { concept } = useSearch({ strict: false }) as SearchById["home"];
  return <HomeScreen host={host} concept={concept} />;
}
