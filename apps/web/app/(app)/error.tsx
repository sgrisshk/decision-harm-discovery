"use client";

import { useEffect } from "react";
import { ErrorState } from "@/components/states";

/**
 * Last-resort boundary for this route group. Expected API failures are
 * already caught and rendered inline by each page via `ErrorState`
 * (`lib/api/display.ts`) — this only catches genuinely unexpected render
 * errors. Next.js redacts thrown error details across the server/client
 * boundary in production, so `error.message` here is intentionally treated
 * as opaque rather than parsed for API-specific fields.
 */
export default function AppGroupError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="appPageHeader">
      <ErrorState
        title="This page could not be displayed"
        message="An unexpected error occurred while rendering this page."
        requestId={error.digest}
      />
      <button type="button" onClick={reset} className="stateBlock-retry">
        Try again
      </button>
    </div>
  );
}
