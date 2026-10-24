/// <reference types="vitest/config" />
import path from "node:path";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

// Dev server proxies the existing stdlib dashboard (pixi run dashboard, port 8765):
//   /api    -> its JSON endpoints
//   /legacy -> its HTML pages, with the prefix stripped (/legacy/graph -> /graph)
// `python -m kb.api` also serves /api and /legacy on 8765, so the same proxy works against either server.
const LEGACY = "http://127.0.0.1:8765";

// The app is served under /app (python -m kb.api, FastAPI spa router) and in dev at http://localhost:5173/app/.
export default defineConfig({
  base: "/app/",
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: {
    proxy: {
      "/api": LEGACY,
      "/static": LEGACY,
      "/legacy": { target: LEGACY, rewrite: (p) => p.replace(/^\/legacy/, "") || "/" },
    },
  },
  build: { outDir: "dist", emptyOutDir: true, sourcemap: false },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
