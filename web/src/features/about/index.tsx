import { Navigate, useSearch } from "@tanstack/react-router";
import { useDataSystemSplit } from "@/app/knowledgeNav";
import { MapCard } from "@/features/home/HomeScreen";
import { useMapHost } from "@/features/home";
import type { SearchById } from "@/routes/search";

const INTRO = {
  id: "what-is-it",
  title: "A Map of the Knowledge That Interests Me",
  byline: "Created by my research agent and me.",
  glossary: true,
};

/** What is it?: the whole map card, the glossary (Raw -> Source -> Concept, reading depths) and Pick a Concept, the concept in `?concept=`. */
export default function WhatIsIt() {
  const host = useMapHost("/what-is-it");
  const { concept } = useSearch({ strict: false }) as SearchById["about"];
  // flag ui.data-system-split: Home carries the glossary, so this page folds into it
  if (useDataSystemSplit()) return <Navigate to="/" search={(concept ? { concept } : {}) as never} replace />;
  return <MapCard host={host} concept={concept} intro={INTRO} />;
}
