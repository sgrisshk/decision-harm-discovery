import Link from "next/link";

type ErrorStateProps = {
  title?: string;
  message: string;
  requestId?: string;
  /** Path to link back to for a full-navigation retry. Ignored when `onRetry` is given. */
  retryHref?: string;
  /**
   * Client-side retry — the page's static shell doesn't change on GitHub Pages, so a `retryHref`
   * navigation to the same URL won't remount the component or re-run its fetch. Callers that fetch
   * in a `useEffect` should pass a callback that resets state and retries instead.
   */
  onRetry?: () => void;
};

/**
 * Reusable error primitive. `role="alert"` so assistive tech announces it
 * immediately. Renders whatever message the caller passes — callers are
 * expected to pass `ApiError.message` (already safe to display) rather than
 * a raw thrown value.
 */
export function ErrorState({
  title = "Something went wrong",
  message,
  requestId,
  retryHref,
  onRetry,
}: ErrorStateProps) {
  return (
    <div className="stateBlock stateBlock--error" role="alert">
      <p className="stateBlock-title">{title}</p>
      <p>{message}</p>
      {requestId && <p className="stateBlock-meta">Request ID: {requestId}</p>}
      {onRetry ? (
        <button type="button" className="stateBlock-retry" onClick={onRetry}>
          Retry
        </button>
      ) : (
        retryHref && (
          <Link className="stateBlock-retry" href={retryHref}>
            Retry
          </Link>
        )
      )}
    </div>
  );
}
