import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "@/app/providers";
import { IS_SHARE } from "@/share/env";
import { readBlob } from "@/share/blob";
import { applyTheme, useTheme } from "@/theme/theme";
import { installTours } from "@/features/tour/tours";
import { loadFlagOverrides } from "@/flags/load";
import "@/features/home/tours"; // the Home → Graph journeys, so `?tour=` works on any route
import "@/features/system/tours"; // the knowledge-base tour (what this app loads, from where)
import "@/features/first-run/tours"; // the first-run card tour (`?tour=first-run`)
import "./index.css";

// A share build carries its data in the page; the embedded DataSource reads it from this global.
if (IS_SHARE) globalThis.KB_EMBEDDED = readBlob() ?? undefined;

applyTheme(useTheme.getState().theme);
installTours();
void loadFlagOverrides(); // server-side runtime overrides; useFlag() re-renders when they land

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
