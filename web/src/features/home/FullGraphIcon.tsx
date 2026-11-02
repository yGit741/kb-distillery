/** Branch-graph glyph for "Open in Full Graph": four filled nodes on three edges, 16px, currentColor. */
export function FullGraphIcon({ className }: { className?: string }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      aria-hidden="true"
      className={className}
      data-testid="full-graph-icon"
    >
      <line x1="4" y1="20" x2="10" y2="11" />
      <line x1="10" y1="11" x2="20" y2="15" />
      <line x1="10" y1="11" x2="14" y2="3" />
      <circle cx="4" cy="20" r="2.6" fill="currentColor" />
      <circle cx="10" cy="11" r="2.6" fill="currentColor" />
      <circle cx="20" cy="15" r="2.6" fill="currentColor" />
      <circle cx="14" cy="3" r="2.6" fill="currentColor" />
    </svg>
  );
}
