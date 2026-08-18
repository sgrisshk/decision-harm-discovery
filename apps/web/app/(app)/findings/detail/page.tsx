import { Suspense } from "react";
import { LoadingState } from "@/components/states";
import { FindingDetailView } from "./FindingDetailView";

export const metadata = {
  title: "Finding — Signal Foundry",
};

// Static export (GitHub Pages, no server): a finding's ID is only known at request time, so this
// can't be a [id] dynamic route (would need every ID pre-rendered via generateStaticParams — see
// ADR/docs/operations/deployment.md). Reads ?id= client-side instead; FindingDetailView sets
// document.title once the finding loads. useSearchParams needs a Suspense boundary — see
// https://nextjs.org/docs/messages/blocking-prerender-client-hook.
export default function FindingDetailPage() {
  return (
    <Suspense fallback={<LoadingState label="Loading finding…" />}>
      <FindingDetailView />
    </Suspense>
  );
}
