/**
 * Build-time share profile. `vite build --mode share` with VITE_SHARE_PROFILE=public|private makes a
 * static, read-only build: the route set is decided at build time
 * (screen.* build flags in meta/flags.toml → routes/modules.share-*.ts) and
 * the data comes from the baked `#kb-data` blob (api/embedded.ts). Any other mode is the normal app.
 */
export type ShareProfile = "public" | "private";

export const SHARE_PROFILE: ShareProfile | null =
  import.meta.env.MODE === "share" ? (import.meta.env.VITE_SHARE_PROFILE === "private" ? "private" : "public") : null;

export const IS_SHARE = SHARE_PROFILE !== null;
