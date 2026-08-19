"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ErrorState, LoadingState } from "@/components/states";
import { EvidencePill } from "@/components/findings/EvidencePill";
import { FeedbackForm } from "@/components/findings/FeedbackForm";
import { FindingCoreContent, Section } from "@/components/findings/FindingCoreContent";
import { ReadinessPill } from "@/components/findings/ReadinessPill";
import { WarningBadge } from "@/components/findings/WarningBadge";
import { getAnalysisRun } from "@/lib/api/analysisRuns";
import { toErrorDisplay } from "@/lib/api/display";
import { getFinding, listFindingFeedback } from "@/lib/api/findings";
import { listPolicyCandidates } from "@/lib/api/policyCandidates";
import { POLICY_CANDIDATE_STATUS_LABELS } from "@/lib/copy/policyLanguage";
import type { Finding, FindingFeedback, PolicyCandidate } from "@/lib/api/types";

const NEXT_STEP_ACTIONS: Record<Finding["policy_readiness"], string[]> = {
  not_ready: ["Flag for review"],
  experiment_only: ["Flag for review", "Design a controlled experiment"],
  shadow_policy: [
    "Flag for review",
    "Design a controlled experiment",
    "Create policy candidate (shadow/log-only — not enforced)",
  ],
  high_confidence: [
    "Flag for review",
    "Design a controlled experiment",
    "Create policy candidate (shadow/log-only — not enforced)",
    "Propose enforced policy candidate for approval",
  ],
};

type Result = { attempt: number } &
  (
    | { finding: Finding; feedback: FindingFeedback[]; policyCandidates: PolicyCandidate[] }
    | { error: unknown }
  );

export function FindingDetailView() {
  const id = useSearchParams().get("id") ?? "";
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<Result | null>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    getFinding(id)
      .then(async (finding) => {
        if (cancelled) return;
        document.title = `Finding ${finding.id.slice(0, 8)} — Signal Foundry`;
        // Feedback history and policy candidates are supplementary, like provenance below — a
        // failure here must not take down the rest of an otherwise-loaded page.
        const feedback = await listFindingFeedback(id).catch(() => []);
        const policyCandidates = await listPolicyCandidates(id).catch(() => []);
        if (!cancelled) setResult({ attempt, finding, feedback, policyCandidates });
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
        title="Could not load this finding"
        message="No finding ID was given."
        retryHref="/findings"
      />
    );
  }

  if (result === null || result.attempt !== attempt) {
    return <LoadingState label="Loading finding…" />;
  }

  if ("error" in result) {
    // A 404 (never promoted / wrong ID) and a genuine network/API failure both go through the
    // same ApiError path — docs/product/finding-detail-screen.md deliberately has no
    // special-cased "not found" page.
    const { message, requestId } = toErrorDisplay(result.error);
    return (
      <ErrorState title="Could not load this finding" message={message} requestId={requestId} onRetry={retry} />
    );
  }

  const { finding, feedback, policyCandidates } = result;

  return (
    <article className="findingDetail">
      <Link href="/findings" className="findingDetail-back">
        ← Back to findings
      </Link>

      <header className="findingDetail-header">
        <h1>{finding.title}</h1>
        <div className="findingDetail-headerPills">
          <EvidencePill level={finding.evidence_level} />
          <ReadinessPill readiness={finding.policy_readiness} />
          <WarningBadge count={finding.evidence.warnings.length} />
        </div>
      </header>

      {finding.lifecycle_status !== "ACTIVE" ? (
        <LifecycleBanner finding={finding} />
      ) : (
        <FindingBody finding={finding} feedback={feedback} policyCandidates={policyCandidates} />
      )}

      <ProvenanceStrip finding={finding} />
    </article>
  );
}

function LifecycleBanner({ finding }: { finding: Finding }) {
  return (
    <div className="findingDetail-banner" role="status">
      {finding.lifecycle_status === "SUPERSEDED" ? (
        <p>This finding has been superseded by a newer analysis.</p>
      ) : (
        <p>This finding was withdrawn.</p>
      )}
    </div>
  );
}

function FindingBody({
  finding,
  feedback,
  policyCandidates,
}: {
  finding: Finding;
  feedback: FindingFeedback[];
  policyCandidates: PolicyCandidate[];
}) {
  return (
    <>
      <FindingCoreContent finding={finding} />

      <Section number={7} title="What you can do next">
        <ul className="findingDetail-actions">
          {NEXT_STEP_ACTIONS[finding.policy_readiness].map((action) => (
            <li key={action}>{action}</li>
          ))}
        </ul>
        {(finding.evidence.failure_modes.length > 0 || finding.evidence.recommended_validation) && (
          <div className="findingDetail-whatCouldChange">
            <p className="findingDetail-effectLabel">What could change</p>
            {finding.evidence.failure_modes.length > 0 && (
              <p>Capped by: {finding.evidence.failure_modes.join(", ")}</p>
            )}
            <p>{finding.evidence.recommended_validation}</p>
          </div>
        )}
        <FeedbackForm findingId={finding.id} initialHistory={feedback} />
      </Section>

      {policyCandidates.length > 0 && (
        <Section number={8} title="Policy candidates">
          <ul className="findingDetail-actions">
            {policyCandidates.map((candidate) => (
              <li key={candidate.id}>
                <Link href={`/policy-candidates/detail?id=${candidate.id}`}>
                  {candidate.title}
                </Link>{" "}
                <span className="findingDetail-meta">
                  ({POLICY_CANDIDATE_STATUS_LABELS[candidate.status]})
                </span>
              </li>
            ))}
          </ul>
        </Section>
      )}
    </>
  );
}

function ProvenanceStrip({ finding }: { finding: Finding }) {
  const [runSummary, setRunSummary] = useState("loading provenance…");

  useEffect(() => {
    let cancelled = false;
    getAnalysisRun(finding.analysis_run_id)
      .then((run) => {
        if (!cancelled) {
          setRunSummary(
            `dataset v${run.dataset_version} · code ${run.code_version} · validation contract ${run.validation_contract_version}`,
          );
        }
      })
      .catch(() => {
        // Provenance is a supplementary trust signal, not the primary content — a failure here
        // must not take down the rest of an otherwise-loaded page.
        if (!cancelled) {
          setRunSummary("provenance unavailable");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [finding.analysis_run_id]);

  return (
    <details className="findingDetail-provenance">
      <summary>Provenance</summary>
      <p className="findingDetail-meta">
        Dataset {finding.dataset_id} · Analysis run {finding.analysis_run_id} · {runSummary} ·
        Generated {new Date(finding.generated_at).toISOString()}
      </p>
    </details>
  );
}
