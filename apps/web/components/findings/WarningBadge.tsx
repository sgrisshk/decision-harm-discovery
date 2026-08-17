/**
 * Header/row badge showing the warning count. Renders nothing when there are
 * none — omission at list/header density reads as clean, not broken (the
 * detail screen's "Warnings & limitations" section separately states
 * "No caveats flagged" explicitly, which is a different, single-item-read
 * context — see docs/product/finding-product-contract.md §6).
 */
export function WarningBadge({ count }: { count: number }) {
  if (count === 0) {
    return null;
  }
  return (
    <span className="pill pill--warning">
      ⚠ {count} {count === 1 ? "caveat" : "caveats"}
    </span>
  );
}
