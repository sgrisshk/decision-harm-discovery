import type { ReactNode } from "react";

type EmptyStateProps = {
  title: string;
  description?: string;
  action?: ReactNode;
};

/**
 * Reusable empty-result primitive — a successful response with zero items.
 * Distinct from `ErrorState`: nothing failed, there is just nothing there
 * yet. Never use this to soften an actual error.
 */
export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div className="stateBlock stateBlock--empty">
      <p className="stateBlock-title">{title}</p>
      {description && <p>{description}</p>}
      {action && <div className="stateBlock-action">{action}</div>}
    </div>
  );
}
