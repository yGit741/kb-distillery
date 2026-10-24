import { Link, Outlet } from "@tanstack/react-router";
import { Command as CommandIcon, Moon, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ROUTES } from "@/routes/registry";
import { ShareFooter } from "@/share/ShareFooter";
import { useTheme } from "@/theme/theme";
import { CommandPalette } from "./CommandPalette";
import { ShareChip } from "./ShareChip";
import { useEmbed } from "./embed";
import { useUi } from "./ui-store";

/** One top nav, ONE theme toggle, ONE command palette, one share chip. Screens render in <Outlet/>. */
export function AppShell() {
  const { theme, toggle } = useTheme();
  const setPaletteOpen = useUi((s) => s.setPaletteOpen);
  const embed = useEmbed();
  return (
    <div className="flex min-h-screen flex-col">
      {!embed && (
      <header className="sticky top-0 z-40 flex h-12 items-center gap-2 border-b bg-card px-4">
        <span className="shrink-0 text-sm font-semibold">Thesis KB</span>
        <nav aria-label="Main" className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          {ROUTES.filter((r) => r.nav).map((r) => (
            <Link
              key={r.id}
              to={r.path}
              activeOptions={{ exact: r.path === "/", includeSearch: false }}
              className="shrink-0 rounded-md px-2.5 py-1.5 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground [&.active]:bg-accent-soft [&.active]:text-primary"
            >
              {r.label}
            </Link>
          ))}
        </nav>
        <ShareChip />
        <Button variant="secondary" size="sm" onClick={() => setPaletteOpen(true)} aria-label="Open command palette">
          <CommandIcon aria-hidden />
          <span className="hidden sm:inline">K</span>
        </Button>
        <Button
          variant="ghost"
          size="icon"
          onClick={toggle}
          aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
        >
          {theme === "dark" ? <Sun aria-hidden /> : <Moon aria-hidden />}
        </Button>
      </header>
      )}
      <main className={embed ? "min-w-0 flex-1" : "mx-auto w-full min-w-0 max-w-6xl flex-1 px-4 py-4"}>
        <Outlet />
      </main>
      <ShareFooter />
      <CommandPalette />
    </div>
  );
}
