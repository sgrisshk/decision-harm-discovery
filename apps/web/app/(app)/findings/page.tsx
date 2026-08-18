import { Suspense } from "react";
import { LoadingState } from "@/components/states";
import { FindingsView } from "./FindingsView";

export const metadata = {
  title: "Findings — Signal Foundry",
};

// Static export (GitHub Pages, no server): all data comes from the client, against
// NEXT_PUBLIC_API_URL. FindingsView reads sort/filter/page from useSearchParams, which requires a
// Suspense boundary so the rest of the route can still be prerendered — see
// https://nextjs.org/docs/messages/blocking-prerender-client-hook.
export default function FindingsPage() {
  return (
    <Suspense fallback={<LoadingState label="Loading findings…" />}>
      <FindingsView />
    </Suspense>
  );
}
