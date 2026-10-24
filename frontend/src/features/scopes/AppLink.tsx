import { Link } from "@tanstack/react-router";
import type { AnchorHTMLAttributes } from "react";

type Props = AnchorHTMLAttributes<HTMLAnchorElement> & { to: string; search?: Record<string, string | undefined> };

/** Router link to another screen with untyped search params (the typed route tree is built from a registry at runtime). */
export function AppLink({ to, search, ...rest }: Props) {
  const clean = search && Object.fromEntries(Object.entries(search).filter(([, v]) => v !== undefined));
  return <Link to={to} search={clean as never} {...(rest as object)} />;
}
