import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "@/app/providers";
import { applyTheme, useTheme } from "@/theme/theme";
import "./index.css";

applyTheme(useTheme.getState().theme);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
