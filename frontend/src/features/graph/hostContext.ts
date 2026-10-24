import { createContext, useContext } from "react";

/** How a tool reaches the rest of the app (the router lives in index.tsx; tests pass plain functions). */
export interface ToolHost {
  /** Go to another screen: `go("/scopes", { draft: key })`. */
  go: (to: string, search?: Record<string, string>) => void;
  /** The same place as a link target, for anchors that open in a new tab. */
  href: (to: string, search?: Record<string, string>) => string;
  openPage: (slug: string) => void;
}

const none: ToolHost = { go: () => {}, href: (to) => to, openPage: () => {} };

export const HostContext = createContext<ToolHost>(none);
export const useToolHost = (): ToolHost => useContext(HostContext);
