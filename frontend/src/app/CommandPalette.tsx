import { useNavigate } from "@tanstack/react-router";
import { ExternalLink } from "lucide-react";
import { useEffect } from "react";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { legacyHref, ROUTES } from "@/routes/registry";
import { IS_SHARE } from "@/share/env";
import { useUi } from "./ui-store";

/** The ONE ⌘K palette, mounted once in AppShell. Screens add commands by extending this list later. */
export function CommandPalette() {
  const { paletteOpen, setPaletteOpen } = useUi();
  const navigate = useNavigate();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen(!useUi.getState().paletteOpen);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setPaletteOpen]);

  const go = (to: string) => {
    setPaletteOpen(false);
    void navigate({ to });
  };

  return (
    <CommandDialog open={paletteOpen} onOpenChange={setPaletteOpen} title="Command palette">
      <CommandInput placeholder="Go to…" />
      <CommandList>
        <CommandEmpty>No matching command.</CommandEmpty>
        <CommandGroup heading="Go to">
          {ROUTES.map((r) => (
            <CommandItem key={r.id} value={`${r.label} ${r.blurb}`} onSelect={() => go(r.path)}>
              <span className="font-medium">{r.label}</span>
              <span className="truncate text-xs text-muted-foreground">{r.blurb}</span>
            </CommandItem>
          ))}
        </CommandGroup>
        {!IS_SHARE && (
        <CommandGroup heading="Legacy pages">
          {ROUTES.filter((r) => !r.ported).map((r) => (
            <CommandItem
              key={r.id}
              value={`legacy ${r.label}`}
              onSelect={() => {
                setPaletteOpen(false);
                window.location.assign(legacyHref(r));
              }}
            >
              <ExternalLink aria-hidden />
              <span>Open legacy {r.label}</span>
            </CommandItem>
          ))}
        </CommandGroup>
        )}
      </CommandList>
    </CommandDialog>
  );
}
