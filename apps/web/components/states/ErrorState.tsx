import Link from "next/link";

type ErrorStateProps = {
  title?: string;
  message: string;
  requestId?: string;
  /** Path to link back to for a full-navigation retry (server components can't re-run a client callback). */
  retryHref?: string;
};

/**
 * Reusable error primitive. `role="alert"` so assistive tech announces it
 * immediately. Renders whatever message the caller passes — callers are
 * expected to pass `ApiError.message` (already safe to display) rather than
 * a raw thrown value.
 */
export function ErrorState({ title = "Something went wrong", message, requestId, retryHref }: ErrorStateProps) {
  return (
    <div className="stateBlock stateBlock--error" role="alert">
      <p className="stateBlock-title">{title}</p>
      <p>{message}</p>
      {requestId && <p className="stateBlock-meta">Request ID: {requestId}</p>}
      {retryHref && (
        <Link className="stateBlock-retry" href={retryHref}>
          Retry
        </Link>
      )}
    </div>
  );
}
