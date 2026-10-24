import { useRouterState } from "@tanstack/react-router";

/**
 * `?embed=1` marks a screen shown inside an iframe (the graph's side reader). Once seen it sticks for the
 * whole document, so in-page links that drop the query keep the clean chrome.
 */
let sticky = false;

export function useEmbed(): boolean {
  const search = useRouterState({ select: (s) => s.location.search }) as Record<string, unknown>;
  if (search.embed !== undefined && search.embed !== false && search.embed !== 0 && search.embed !== "0") sticky = true;
  return sticky;
}

/** Test helper: forget the sticky flag between renders. */
export const resetEmbed = (): void => {
  sticky = false;
};
