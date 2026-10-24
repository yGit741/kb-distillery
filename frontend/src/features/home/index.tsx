import { useNavigate } from "@tanstack/react-router";
import { useMemo } from "react";
import { HomeScreen, type HomeHost } from "./HomeScreen";
import { curatedCards } from "./curated";

export const ported = true;

const base = (import.meta.env.BASE_URL as string).replace(/\/$/, "");

/** Home: the router supplies navigation to the full graph; everything else is in HomeScreen. */
export default function Home() {
  const navigate = useNavigate();
  const host = useMemo<HomeHost>(
    () => ({
      // `from=home` gives the graph a way back
      openGraph: (search) => void navigate({ to: "/graph" as "/", search: { ...search, from: "home" } as never }),
      graphHref: (search) => `${base}/graph?${new URLSearchParams({ ...search, from: "home" }).toString()}`,
      openPage: (slug) => void navigate({ to: `/pages/${encodeURIComponent(slug)}` as "/" }),
      pageHref: (slug) => `${base}/pages/${encodeURIComponent(slug)}`,
    }),
    [navigate],
  );
  const cards = useMemo(() => curatedCards(), []);
  return <HomeScreen host={host} cards={cards} />;
}
