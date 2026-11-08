import { Link } from "@tanstack/react-router";
import { useApiQuery } from "@/lib/useApiQuery";

/**
 * A slim, non-blocking notice under the header when the served knowledge base is read-only (an example kb,
 * `[kb] read_only`, or KB_READ_ONLY): every write is refused by the server, so say so and point at Start.
 * Builds without /api/kb (share, static) have no kb info and show nothing.
 */
export function ReadOnlyBanner() {
  const q = useApiQuery(["kb"], (d) => d.getKb(), { staleTime: Infinity, retry: false });
  if (!q.data?.read_only) return null;
  return (
    <div role="status" data-testid="read-only-banner" className="border-b bg-muted px-4 py-1.5 text-center text-sm text-muted-foreground">
      Read-only example knowledge base. Create your own to add sources.{" "}
      <Link to={"/start" as never} className="font-medium text-primary underline-offset-2 hover:underline">
        Open the Start screen
      </Link>
    </div>
  );
}
