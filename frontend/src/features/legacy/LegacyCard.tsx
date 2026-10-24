import { ArrowUpRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ROUTE_DEFS, legacyHref } from "@/routes/defs";

/** Placeholder for a screen that has not been ported: one link to the server-rendered page. */
export function LegacyCard({ id }: { id: string }) {
  const route = ROUTE_DEFS.find((r) => r.id === id);
  if (!route) return null;
  return (
    <Card className="mx-auto max-w-xl">
      <CardHeader>
        <CardTitle>{route.label}</CardTitle>
        <CardDescription>{route.blurb}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p className="text-sm text-muted-foreground">This screen has not moved to the new app yet.</p>
        <Button asChild className="self-start">
          <a href={legacyHref(route)}>
            Open the legacy page <ArrowUpRight aria-hidden />
          </a>
        </Button>
      </CardContent>
    </Card>
  );
}
