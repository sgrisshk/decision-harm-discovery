import { Suspense } from "react";
import { LoadingState } from "@/components/states";
import { PolicyCandidateDetailView } from "./PolicyCandidateDetailView";

export const metadata = {
  title: "Policy candidate — Signal Foundry",
};

// Static export (GitHub Pages, no server) — same reasoning as app/(app)/findings/detail/page.tsx:
// a candidate's ID is only known at request time, so this reads ?id= client-side instead of a
// [id] dynamic route. useSearchParams needs a Suspense boundary.
export default function PolicyCandidateDetailPage() {
  return (
    <Suspense fallback={<LoadingState label="Loading policy candidate…" />}>
      <PolicyCandidateDetailView />
    </Suspense>
  );
}
