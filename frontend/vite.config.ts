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
//
// `vite build --mode share` is the static, read-only build for the shared site (kb.share.build --app):
// served from the site root, with the screens it includes decided HERE, at build time. The profile comes
// from VITE_SHARE_PROFILE (public = graph + pages, private = + lifecycle; anything else is public, the
// safe side). The route registry then imports a literal screen list (src/routes/modules.share-*.ts), so
// chat, ops, pipeline and scopes are not in the bundle at all.
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
        "/api": LEGACY,
        "/static": LEGACY,
        "/legacy": { target: LEGACY, rewrite: (p: string) => p.replace(/^\/legacy/, "") || "/" },
      },
    },
    build: { outDir: share ? path.resolve(__dirname, "dist-share", profile) : "dist", emptyOutDir: true, sourcemap: false },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./src/test/setup.ts"],
      css: false,
    },
  };
});
