/**
 * The Think corner's mark: a brain outline with a centre line and two short folds. Drawn here (24 px grid,
 * 1.75 stroke, round caps) so it matches the lucide line icons beside it. Size follows the neighbours: 22 px.
 */
export function ThinkIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="22"
      height="22"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      data-icon="think"
      aria-hidden
    >
      <path d="M12 4.5c-1.6-1.6-4.6-1.1-5.3 1.2C4.6 6.1 3.4 8.3 4.3 10.1c-1.2 1.6-.6 4 1.3 4.7.2 2.2 2.5 3.4 4.3 2.4.6.9 1.4 1.3 2.1 1.3s1.5-.4 2.1-1.3c1.8 1 4.1-.2 4.3-2.4 1.9-.7 2.5-3.1 1.3-4.7.9-1.8-.3-4-2.4-4.4C16.6 3.4 13.6 2.9 12 4.5Z" />
      <path d="M12 4.5v14" />
      <path d="M8.5 9.5c1.2.3 2 1.1 2.3 2.2" />
      <path d="M15.5 9.5c-1.2.3-2 1.1-2.3 2.2" />
    </svg>
  );
}
