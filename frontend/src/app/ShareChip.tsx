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
  return (
    <a
      href={chip.href}
      title={chip.title}
      className="hidden sm:inline-flex"
      aria-label={`Share status: ${chip.label}`}
      data-testid="share-chip"
    >
      <Badge variant={VARIANT[chip.cls] ?? "default"}>{chip.label}</Badge>
    </a>
  );
}
