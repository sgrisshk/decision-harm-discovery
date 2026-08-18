import Link from "next/link";
import type { ReactNode } from "react";
import { Nav } from "@/components/nav";
import { NavUser } from "@/components/nav-user";
import "./app-shell.css";

const isDev = process.env.NODE_ENV !== "production";

/**
 * Shell for the application surfaces (as opposed to the marketing page at
 * `/`): persistent nav plus a content container. Intentionally not a
 * dashboard — a fixed set of top-level routes, not widgets/metrics.
 */
export default function AppLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <div className="appShell">
      <header className="appHeader">
        <Link className="appBrand" href="/" aria-label="Signal Foundry home">
          <span className="appBrandMark">SF</span>
          Signal Foundry
        </Link>
        <Nav />
        <NavUser />
        {isDev && (
          <Link className="appDevLink" href="/dev/status">
            Dev: API status
          </Link>
        )}
      </header>
      <main className="appMain">{children}</main>
    </div>
  );
}
