import { registerTour } from "@/features/tour/tours";

const CARD = '[data-tour="first-run"]';

registerTour("first-run", [
  {
    go: "/graph",
    target: "#first-run-title",
    pad: 10,
    title: "An empty knowledge base starts here",
    body: "Three steps: **add** sources, **digest** them, then watch the graph fill in. Nothing is sent anywhere until you start a digest.",
    place: "bottom",
  },
  { target: `${CARD} [aria-label="Drop files here"]`, title: "Drop files", body: "Papers, notes and articles go to the inbox. Click the zone to pick files instead." },
  { target: `${CARD} form[aria-label="Link a local folder"]`, title: "Or link a folder", body: "Paste a folder path and its files are catalogued in place, without copying them." },
  { target: `${CARD} section[aria-label="Digest jobs"]`, title: "Digest what you added", body: "Pick sources, **preview the cost** on each backend, then start. You can cancel while it runs.", place: "top" },
]);
