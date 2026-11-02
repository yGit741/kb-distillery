/**
 * The header's middle: a screen may portal its own search box here (the graph's Finder does).
 * A leaf module on purpose: AppShell imports the route registry, which imports every screen, so a screen
 * must never import AppShell back (the cycle left `modules` undefined in registry.ts).
 */
export const HEADER_SLOT_ID = "app-header-slot";
