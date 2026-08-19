import { Suspense } from "react";
import { LoadingState } from "@/components/states";
import { PolicyBacktestView } from "./PolicyBacktestView";

export const metadata = {
  title: "Policy backtest — Signal Foundry",
};

// Static export (GitHub Pages, no server) — same reasoning as findings/detail and
// policy-candidates/detail: reads ?id= client-side instead of a [id] dynamic route.
export default function PolicyBacktestPage() {
  return (
    <Suspense fallback={<LoadingState label="Loading policy candidate…" />}>
      <PolicyBacktestView />
    </Suspense>
  );
}
