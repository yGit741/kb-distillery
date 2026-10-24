import { SHARE_PROFILE } from "./env";

/** One line naming what the reader is looking at: version, commit, profile, build date. */
export function ShareFooter() {
  const m = globalThis.KB_EMBEDDED?.meta;
  if (!SHARE_PROFILE || !m) return null;
  return (
    <footer className="border-t px-4 py-2 text-xs text-muted-foreground" data-testid="share-footer">
      kb {m.kb_version} · {m.content_sha.slice(0, 7)} · {m.profile} · built {m.built_at}
    </footer>
  );
}
