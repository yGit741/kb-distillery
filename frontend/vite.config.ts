/// <reference types="vitest/config" />
import path from "node:path";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

// Dev server proxies the existing stdlib dashboard (pixi run dashboard, port 8765):
//   /api    -> its JSON endpoints
//   /legacy -> its HTML pages, with the prefix stripped (/legacy/graph -> /graph)
const LEGACY = "http://127.0.0.1:8765";

export default defineConfig({
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
