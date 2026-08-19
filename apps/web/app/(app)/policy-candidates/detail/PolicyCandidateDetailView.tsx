"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { ErrorState, LoadingState } from "@/components/states";
import { EvidencePill } from "@/components/findings/EvidencePill";
import { ExposureFigure } from "@/components/findings/ExposureFigure";
import { PolicyCandidateActions } from "@/components/policies/PolicyCandidateActions";
import { toErrorDisplay } from "@/lib/api/display";
import { getPolicyCandidate } from "@/lib/api/policyCandidates";
import { POLICY_CANDIDATE_STATUS_LABELS } from "@/lib/copy/policyLanguage";
import type { PolicyCandidate } from "@/lib/api/types";

type Result = { attempt: number } & ({ candidate: PolicyCandidate } | { error: unknown });

export function PolicyCandidateDetailView() {
  const id = useSearchParams().get("id") ?? "";
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<Result | null>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    getPolicyCandidate(id)
      .then((candidate) => {
        if (cancelled) return;
        document.title = `Policy candidate ${candidate.id.slice(0, 8)} — Signal Foundry`;
        setResult({ attempt, candidate });
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

  const { candidate } = result;

  return (
    <article className="findingDetail">
      <Link href={`/findings/detail?id=${candidate.finding_id}`} className="findingDetail-back">
        ← Back to finding
      </Link>

      <header className="findingDetail-header">
        <h1>{candidate.title}</h1>
        <div className="findingDetail-headerPills">
          <EvidencePill level={candidate.evidence_snapshot.evidence_level} />
          <span className="pill">{POLICY_CANDIDATE_STATUS_LABELS[candidate.status]}</span>
        </div>
      </header>

      <Section number={1} title="The rule">
        <p>{candidate.rationale}</p>
        <details className="findingDetail-disclosure">
          <summary>View technical trigger definition</summary>
          <ul className="findingDetail-conditions">
            {candidate.trigger_conditions.map((condition, index) => (
              <li key={index}>
                <code>
                  {String(condition.feature)} {String(condition.operator)}{" "}
                  {JSON.stringify(condition.value)}
                </code>
              </li>
            ))}
          </ul>
        </details>
        <p className="findingDetail-meta">
          {candidate.mode === "SHADOW" ? "Shadow mode (log-only, never enforced)" : candidate.mode}
          {" · "}Effective from {candidate.effective_from}
        </p>
      </Section>

      <Section number={2} title="Scope">
        <p>{candidate.effective_population ?? "Every future decision matching the trigger."}</p>
        {candidate.scope_narrowing_features.length > 0 && (
          <p className="findingDetail-meta">
            Narrowed by: {candidate.scope_narrowing_features.join(", ")}
          </p>
        )}
      </Section>

      <Section number={3} title="Expected benefit (exposure, not a guarantee)">
        <p className="findingDetail-exposureHeadline">
          <ExposureFigure estimate={candidate.expected_benefit_snapshot.historical_impact} />
        </p>
        <p className="findingDetail-disclaimer">
          This reflects the source finding&apos;s observed history, not a validated forward-looking
          benefit — that requires a historical backtest (below, once approved).
        </p>
      </Section>

      <Section number={4} title="Action">
        <p>{candidate.action_detail ?? "Not yet set — required before this candidate can advance."}</p>
      </Section>

      <Section number={5} title="What you can do next">
        <PolicyCandidateActions candidate={candidate} />
      </Section>
    </article>
  );
}

function Section({ number, title, children }: { number: number; title: string; children: ReactNode }) {
  return (
    <section className="findingDetail-section">
      <h2>
        <span className="findingDetail-sectionNumber">{number}</span> {title}
      </h2>
      {children}
    </section>
  );
}
