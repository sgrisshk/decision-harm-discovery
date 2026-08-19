import { LoadingState } from "@/components/states";
import { Suspense } from "react";
import { ReviewSessionView } from "./ReviewSessionView";

export const metadata = {
  title: "Review session — Signal Foundry",
};

// Static export (GitHub Pages, no server) — client-fetched, same pattern as every other data
// view since ADR-032. No ?id= here (the queue isn't keyed to one finding), but useSearchParams
// isn't used either, so no Suspense boundary is strictly required — kept for a consistent
// loading shell with every other view in this app.
export default function ReviewSessionPage() {
  return (
    <Suspense fallback={<LoadingState label="Loading review session…" />}>
      <ReviewSessionView />
    </Suspense>
  );
}
