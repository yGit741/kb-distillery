import { Boxes, MessageSquare, MousePointerSquareDashed, ShoppingBasket, TextSearch } from "lucide-react";
import { ChatDock, ChatToolPanel } from "./ChatDock";
import { CorpusDrawer } from "../CorpusDrawer";
import { useLayer } from "../layerStore";
import { registerMenuItem } from "../menu";
import { BasketPanel } from "./BasketPanel";
import { QueryPanel } from "./QueryPanel";
import { RawPanel } from "./RawPanel";
import { RegionOverlay } from "./RegionOverlay";
import { SelectionPanel } from "./SelectionPanel";
import { registerTool } from ".";

/**
 * The selection, basket and data-layer tools plus the citation genealogy menu entry. The core ships none
 * of them: importing this file (GraphScreen does) is the registration.
 */
// the chat dock is part of the local app only; a share build has no chat (see ChatDock.tsx)
if (import.meta.env.MODE !== "share") {
  registerTool({
    id: "chat",
    label: "Ask (chat)",
    icon: <MessageSquare aria-hidden />,
    shortcut: "a",
    panel: () => <ChatToolPanel />,
    overlay: () => <ChatDock />,
  });
}

registerTool({
  id: "selection",
  label: "Selection tools",
  icon: <MousePointerSquareDashed aria-hidden />,
  shortcut: "s",
  panel: (ctx) => <SelectionPanel ctx={ctx} />,
  overlay: (ctx) => <RegionOverlay ctx={ctx} />,
});

registerTool({
  id: "basket",
  label: "Scope draft",
  icon: <ShoppingBasket aria-hidden />,
  shortcut: "b",
  panel: (ctx) => <BasketPanel ctx={ctx} />,
});

registerTool({
  id: "raw",
  label: "Raw files",
  icon: <Boxes aria-hidden />,
  shortcut: "r",
  panel: (ctx) => <RawPanel ctx={ctx} />,
  overlay: (ctx) => <CorpusDrawer ctx={ctx} />,
});

// read-only graph queries over the local API; a share build has no query endpoint
if (import.meta.env.MODE !== "share") {
  registerTool({
    id: "query",
    label: "Graph query",
    icon: <TextSearch aria-hidden />,
    panel: (ctx) => <QueryPanel ctx={ctx} />,
    featureFlag: "graph-relations",
  });
}

registerMenuItem(
  {
    id: "genealogy",
    label: "Open citation genealogy",
    hint: "2 hops",
    enabled: (n) => n.type === "paper",
    why: "papers only",
    run: (n) => useLayer.getState().openDrawer({ kind: "genealogy", focus: n.id }),
  },
  "page",
);
