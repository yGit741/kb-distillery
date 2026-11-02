/// <reference types="vitest/config" />
import path from "node:path";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

// Dev server proxies the API server (pixi run app, port 8765): /api -> its JSON endpoints.
// KB_API points a worktree's dev server at its own backend (e.g. KB_API=http://127.0.0.1:8790).
const API_TARGET = process.env.KB_API || "http://127.0.0.1:8765";

// The app is served under /app (python -m kb_distillery.server, FastAPI spa router) and in dev at http://localhost:5173/app/.
//
// `vite build --mode share` is the static, read-only build for the shared site (kb_distillery.publish.site.build):
// served from the site root, with the screens it includes decided HERE, at build time. The profile comes
// from VITE_SHARE_PROFILE (anything but "private" is public, the safe side). The route registry then
// imports a literal screen list (src/routes/modules.share-*.ts, generated from the screen.* build flags in
// meta/flags.toml by `pixi run flags-gen`), so chat, ops, pipeline and scopes are not in the bundle at all.
export default defineConfig(({ mode }) => {
  const share = mode === "share";
  const profile = process.env.VITE_SHARE_PROFILE === "private" ? "private" : "public";
  const src = path.resolve(__dirname, "src");
  return {
    base: share ? "/" : "/app/",
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: [
        ...(share ? [{ find: /^@\/routes\/modules$/, replacement: path.join(src, `routes/modules.share-${profile}.ts`) }] : []),
        { find: "@", replacement: src },
      ],
    },
    define: share ? { "import.meta.env.VITE_SHARE_PROFILE": JSON.stringify(profile) } : {},
    server: {
      proxy: {
        "/api": API_TARGET,
      },
    },
    build: { outDir: share ? path.resolve(__dirname, "dist-share", profile) : path.resolve(__dirname, "../src/kb_distillery/_webapp"), emptyOutDir: true, sourcemap: false },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./src/test/setup.ts"],
      css: false,
      // e2e/ runs under node --test with a real browser (pixi run test-e2e), not vitest
      include: ["src/**/*.test.{ts,tsx}"],
      // inside a ship gate (KB_GATE_SLOT_HELD) cap the pool so one web run cannot take every core; a developer's own run is uncapped
      ...(process.env.KB_GATE_SLOT_HELD ? { maxWorkers: 4 } : {}),
    },
  };
});
