"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ErrorState, LoadingState } from "@/components/states";
import { EvidencePill } from "@/components/findings/EvidencePill";
import { TriggerBacktestForm } from "@/components/policies/TriggerBacktestForm";
import { toErrorDisplay } from "@/lib/api/display";
import { getPolicyCandidate, listBacktestRuns } from "@/lib/api/policyCandidates";
import type { PolicyBacktestRun, PolicyCandidate } from "@/lib/api/types";

type Result = { attempt: number } & (
  | { candidate: PolicyCandidate; runs: PolicyBacktestRun[] }
  | { error: unknown }
);

/**
 * `docs/product/policy-backtest-screen.md`. "A backtest is a mechanical replay... not a causal
 * estimate, not a second piece of evidence, not an experiment" (§0) — this screen never implies
 * otherwise: the evidence pill reused here is the source finding's own, unchanged by anything on
 * this page.
 */
export function PolicyBacktestView() {
  const id = useSearchParams().get("id") ?? "";
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<Result | null>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    getPolicyCandidate(id)
      .then(async (candidate) => {
        if (cancelled) return;
        document.title = `Backtest ${candidate.id.slice(0, 8)} — Signal Foundry`;
        // Run history is supplementary — a failure here must not take down the trigger action.
        const runs = await listBacktestRuns(id).catch(() => []);
        if (!cancelled) setResult({ attempt, candidate, runs });
      })
      .catch((error: unknown) => {
        if (!cancelled) setResult({ attempt, error });
      });
    return () => {
      cancelled = true;
    };
  }, [id, attempt]);

  const retry = () => setAttempt((current) => current + 1);

  if (!id) {
    return (
      <ErrorState
        title="Could not load this policy candidate"
        message="No policy candidate ID was given."
        retryHref="/findings"
      />
    );
  }

  if (result === null || result.attempt !== attempt) {
    return <LoadingState label="Loading policy candidate…" />;
  }

  if ("error" in result) {
    const { message, requestId } = toErrorDisplay(result.error);
    return (
      <ErrorState
        title="Could not load this policy candidate"
        message={message}
        requestId={requestId}
        onRetry={retry}
      />
    );
  }

  const { candidate, runs } = result;

  return (
    <article className="findingDetail">
      <Link href={`/policy-candidates/detail?id=${id}`} className="findingDetail-back">
        ← Back to policy candidate
      </Link>

      <header className="findingDetail-header">
        <h1>Historical backtest: {candidate.title}</h1>
        <div className="findingDetail-headerPills">
          <EvidencePill level={candidate.evidence_snapshot.evidence_level} />
        </div>
        <p className="findingDetail-meta">
          Backtested against the future-holdout window — a mechanical replay, not a forecast.
        </p>
      </header>

      <TriggerBacktestForm candidateId={id} initialRuns={runs} />
    </article>
  );
}
