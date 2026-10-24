import { ArrowUpRight, BookOpen, Shuffle } from "lucide-react";
import type { MouseEvent } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Markdown } from "@/components/Markdown";
import { Loading } from "@/components/states";
import { useApiQuery } from "@/lib/useApiQuery";
import { typeColor } from "@/theme/palette";
import { NODE_CAPTION, excerpt, neighbourhood, type NodeSample, type Vault } from "./samplers";
import type { HomeHost } from "./HomeScreen";

/** A plain click navigates in-app; modified clicks keep the real link (new tab, copy). */
const inApp = (go: () => void) => (e: MouseEvent) => {
  if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
  e.preventDefault();
  go();
};

/** One knowledge node as text: facts, the opening of the page, its strongest neighbours. */
export function NodeCard({ sample, vault, host, onReroll }: { sample: NodeSample; vault: Vault; host: HomeHost; onReroll: () => void }) {
  const n = vault.byId.get(sample.id);
  const page = useApiQuery(["page", sample.id], (d) => d.getPage(sample.id), { staleTime: 5 * 60_000 });
  if (!n) return null;
  const text = page.data ? excerpt(page.data.markdown, undefined, n.title) : n.preview;
  const graph = { pages: neighbourhood(vault, sample.id).nodes.join(","), select: sample.id, focus: sample.id };
  const titleOf = (id: string) => vault.byId.get(id)?.title || id;
  return (
    <Card className="flex min-w-0 flex-col" data-tour={`home-node-${sample.kind}`}>
      <CardHeader>
        <CardDescription>{NODE_CAPTION[sample.kind]}</CardDescription>
        <CardTitle className="text-lg leading-snug">
          <a
            href={host.pageHref(sample.id)}
            title={n.title || n.id}
            className="line-clamp-4 hover:underline"
            onClick={inApp(() => host.openPage(sample.id))}
          >
            {n.title || n.id}
          </a>
        </CardTitle>
        <div className="flex flex-wrap gap-1.5 pt-1">
          <Badge variant="outline" className="gap-1.5">
            <span aria-hidden className="size-2 rounded-full" style={{ background: typeColor(n.type) }} />
            {n.type}
          </Badge>
          {n.depth && <Badge variant="outline">{n.depth}</Badge>}
          {n.status && n.layer !== "source" && <Badge variant="outline">{n.status}</Badge>}
          {n.year ? <Badge variant="outline">{n.year}</Badge> : null}
          {n.areas.map((a) => (
            <Badge key={a}>{a}</Badge>
          ))}
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 py-0">
        {page.isPending && !text ? (
          <Loading label="Loading the page" rows={2} />
        ) : (
          <div dir="auto" className="max-h-56 overflow-hidden text-sm [mask-image:linear-gradient(to_bottom,black_75%,transparent)]">
            <Markdown resolveSlug={(s) => (vault.byId.has(s) ? s : null)}>{text}</Markdown>
          </div>
        )}
        {sample.neighbours.length > 0 && (
          <div className="flex flex-col gap-1.5">
            <span className="text-xs text-muted-foreground">Linked with</span>
            <div className="flex flex-wrap gap-1.5">
              {sample.neighbours.map((id) => (
                <a
                  key={id}
                  href={host.pageHref(id)}
                  onClick={inApp(() => host.openPage(id))}
                  className="inline-flex max-w-full items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs hover:bg-accent"
                  title={titleOf(id)}
                >
                  <span aria-hidden className="size-2 shrink-0 rounded-full" style={{ background: typeColor(vault.byId.get(id)?.type) }} />
                  <span className="truncate">{titleOf(id)}</span>
                </a>
              ))}
            </div>
          </div>
        )}
      </CardContent>
      <div className="mt-auto flex flex-wrap items-center justify-end gap-1 p-4 pt-3">
        <Button variant="ghost" size="sm" onClick={onReroll} aria-label={`Another ${sample.kind} note`}>
          <Shuffle aria-hidden /> Another
        </Button>
        <Button variant="ghost" size="sm" asChild>
          <a href={host.pageHref(sample.id)} onClick={inApp(() => host.openPage(sample.id))}>
            <BookOpen aria-hidden /> Read
          </a>
        </Button>
        <Button variant="outline" size="sm" asChild>
          <a href={host.graphHref(graph)} onClick={inApp(() => host.openGraph(graph))}>
            Open in full graph <ArrowUpRight aria-hidden />
          </a>
        </Button>
      </div>
    </Card>
  );
}
