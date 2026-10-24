import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "@/app/providers";
import { IS_SHARE } from "@/share/env";
import { readBlob } from "@/share/blob";
import { applyTheme, useTheme } from "@/theme/theme";
import "./index.css";

// A share build carries its data in the page; the embedded DataSource reads it from this global.
if (IS_SHARE) globalThis.KB_EMBEDDED = readBlob() ?? undefined;

applyTheme(useTheme.getState().theme);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
