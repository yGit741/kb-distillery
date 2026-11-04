import { useQuery } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { useDataSource } from "@/api";

const VARIANT: Record<string, "ok" | "warn" | "bad" | "default"> = { ok: "ok", warn: "warn", bad: "bad" };

/** Share deploy status from /api/share/status. Renders nothing until something was deployed. */
export function ShareChip() {
  const ds = useDataSource();
  const { data } = useQuery({ queryKey: ["share-status"], queryFn: () => ds.getShareStatus(), retry: false });
  const chip = data?.chip;
  if (!chip) return null;
  const badge = <Badge variant={VARIANT[chip.cls] ?? "default"}>{chip.label}</Badge>;
  const label = `Share status: ${chip.label}`;
  // No destination (no publisher configured) = a plain status, not a link: an empty href is a dead 20px click target.
  if (!chip.href) {
    return (
      <span title={chip.title} className="hidden min-h-6 items-center sm:inline-flex" role="status" aria-label={label} data-testid="share-chip">
        {badge}
      </span>
    );
  }
  return (
    <a href={chip.href} title={chip.title} className="hidden min-h-6 items-center sm:inline-flex" aria-label={label} data-testid="share-chip">
      {badge}
    </a>
  );
}
