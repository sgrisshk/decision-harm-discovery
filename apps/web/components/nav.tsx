import Link from "next/link";

const links: { href: string; label: string }[] = [
  { href: "/", label: "Home" },
  { href: "/datasets", label: "Datasets" },
  { href: "/findings", label: "Findings" },
];

/**
 * Primary application navigation. Server component — no client JS needed
 * for a static link list. Dev-only links (e.g. the status view) are added by
 * the layout, not here, so this stays environment-agnostic.
 */
export function Nav() {
  return (
    <nav className="appNav" aria-label="Primary">
      <ul>
        {links.map((link) => (
          <li key={link.href}>
            <Link href={link.href}>{link.label}</Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
