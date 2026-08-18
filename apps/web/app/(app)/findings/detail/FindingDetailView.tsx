"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { ErrorState, LoadingState } from "@/components/states";
import { EvidencePill } from "@/components/findings/EvidencePill";
import { ExposureFigure } from "@/components/findings/ExposureFigure";
import { FeedbackForm } from "@/components/findings/FeedbackForm";
import { ReadinessPill } from "@/components/findings/ReadinessPill";
import { WarningBadge } from "@/components/findings/WarningBadge";
import { getAnalysisRun } from "@/lib/api/analysisRuns";
import { toErrorDisplay } from "@/lib/api/display";
import { getFinding, listFindingFeedback } from "@/lib/api/findings";
import { EVIDENCE_LABELS } from "@/lib/copy/findingLanguage";
import type { EvidenceLevel, Finding, FindingFeedback } from "@/lib/api/types";

const EVIDENCE_LADDER: EvidenceLevel[] = [
  "descriptive_observation",
  "predictive_association",
  "adjusted_observational_association",
  "quasi_causal_evidence",
  "experimental_evidence",
];

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

export function FindingDetailView() {
  const id = useSearchParams().get("id") ?? "";

  const [finding, setFinding] = useState<Finding | null>(null);
  const [feedback, setFeedback] = useState<FindingFeedback[]>([]);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(() => {
    setError(null);
    setFinding(null);
    setFeedback([]);
    getFinding(id)
      .then((loaded) => {
        setFinding(loaded);
        document.title = `Finding ${loaded.id.slice(0, 8)} — Signal Foundry`;
        // Feedback history is supplementary, like provenance below — a failure here must not
        // take down the rest of an otherwise-loaded page.
        listFindingFeedback(id)
          .then(setFeedback)
          .catch(() => setFeedback([]));
      })
      .catch((err: unknown) => setError(err));
  }, [id]);

  useEffect(load, [load]);

  if (!id) {
    return (
      <ErrorState
        title="Could not load this finding"
        message="No finding ID was given."
        retryHref="/findings"
      />
    );
  }

  if (error) {
    // A 404 (never promoted / wrong ID) and a genuine network/API failure both go through the
    // same ApiError path — docs/product/finding-detail-screen.md deliberately has no
    // special-cased "not found" page.
    const { message, requestId } = toErrorDisplay(error);
    return (
      <ErrorState title="Could not load this finding" message={message} requestId={requestId} onRetry={load} />
    );
  }

  if (finding === null) {
    return <LoadingState label="Loading finding…" />;
  }

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
        <FindingBody finding={finding} feedback={feedback} />
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

function FindingBody({ finding, feedback }: { finding: Finding; feedback: FindingFeedback[] }) {
  const totalPopulation = finding.exposed_records + finding.comparison_records;
  const exposedShare =
    totalPopulation > 0 ? ((finding.exposed_records / totalPopulation) * 100).toFixed(1) : null;
  const hasAlternatives =
    finding.evidence.controlled_variables.length > 0 ||
    finding.evidence.potential_confounders.length > 0;

  return (
    <>
      <Section number={1} title="What we found">
        <p>{finding.summary}</p>
        <details className="findingDetail-disclosure">
          <summary>View technical rule definition</summary>
          <ul className="findingDetail-conditions">
            {finding.pattern.conditions.map((condition, index) => (
              <li key={index}>
                <code>
                  {String(condition.feature)} {String(condition.operator)}{" "}
                  {JSON.stringify(condition.value)}
                </code>
              </li>
            ))}
          </ul>
        </details>
      </Section>

      <Section number={2} title="Who this applies to">
        <p>
          {finding.exposed_records.toLocaleString("en-US")} of{" "}
          {totalPopulation.toLocaleString("en-US")} bookings
          {exposedShare !== null ? ` (${exposedShare}%)` : ""}
        </p>
        <p className="findingDetail-meta">Clustered by {finding.clustering_key}</p>
      </Section>

      <Section number={3} title="Money at stake">
        <p className="findingDetail-exposureHeadline">
          <ExposureFigure estimate={finding.impact.historical_impact} />{" "}
          <span className="findingDetail-meta">
            ({finding.impact.outcome_name}, historical period only)
          </span>
        </p>
        {finding.impact.annualization_justified && finding.impact.annualized_impact ? (
          <p>
            Annualized estimate:{" "}
            <ExposureFigure estimate={finding.impact.annualized_impact} />
          </p>
        ) : (
          <p className="findingDetail-meta">Not enough history to project forward.</p>
        )}
        <p className="findingDetail-disclaimer">
          This reflects observed history, not a guaranteed future saving.
        </p>
      </Section>

      <Section number={4} title="How strong is the evidence">
        <EvidenceLadder current={finding.evidence_level} />
        <div className="findingDetail-effects">
          <div>
            <span className="findingDetail-effectLabel">Raw effect</span>
            <span className="findingDetail-effectValue">
              {finding.evidence.raw_effect.value.toFixed(1)} {finding.evidence.raw_effect.unit}
            </span>
            <span className="findingDetail-meta">
              Descriptive, unadjusted, no interval — not a validated estimate.
            </span>
          </div>
          <div>
            <span className="findingDetail-effectLabel">Adjusted effect</span>
            {finding.evidence.adjusted_effect ? (
              <>
                <span className="findingDetail-effectValue">
                  {finding.evidence.adjusted_effect.value.toFixed(1)} (
                  {finding.evidence.adjusted_effect.ci_low.toFixed(1)}–
                  {finding.evidence.adjusted_effect.ci_high.toFixed(1)},{" "}
                  {(finding.evidence.adjusted_effect.confidence_level * 100).toFixed(0)}% CI)
                </span>
                <span className="findingDetail-meta">
                  Method: {finding.evidence.adjusted_effect.method}
                </span>
              </>
            ) : (
              <span className="findingDetail-meta">Not yet adjusted.</span>
            )}
          </div>
        </div>
        {finding.evidence.controlled_variables.length > 0 && (
          <p>Adjusted for: {finding.evidence.controlled_variables.join(", ")}</p>
        )}
        <p>Stability: {finding.evidence.temporal_stability || "Not evaluated."}</p>
        <p className="findingDetail-permittedLanguage">{finding.evidence.permitted_language}</p>
      </Section>

      <Section number={5} title="Alternative explanations checked">
        {hasAlternatives ? (
          <>
            {finding.evidence.controlled_variables.length > 0 && (
              <p>
                <strong>Adjusted for:</strong> {finding.evidence.controlled_variables.join(", ")}
              </p>
            )}
            {finding.evidence.potential_confounders.length > 0 && (
              <p>
                <strong>Considered, still possible:</strong>{" "}
                {finding.evidence.potential_confounders.join(", ")}
              </p>
            )}
          </>
        ) : (
          <p>Not yet tested against alternative explanations.</p>
        )}
      </Section>

      <Section number={6} title="Warnings & limitations">
        {finding.evidence.warnings.length > 0 ? (
          <ul>
            {finding.evidence.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        ) : (
          <p>No caveats flagged.</p>
        )}
      </Section>

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
    </>
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

function EvidenceLadder({ current }: { current: EvidenceLevel }) {
  const currentIndex = EVIDENCE_LADDER.indexOf(current);
  return (
    <ol className="evidenceLadder">
      {EVIDENCE_LADDER.map((level, index) => (
        <li
          key={level}
          className={
            index === currentIndex
              ? "evidenceLadder-step evidenceLadder-step--current"
              : index < currentIndex
                ? "evidenceLadder-step evidenceLadder-step--passed"
                : "evidenceLadder-step"
          }
        >
          {EVIDENCE_LABELS[level]}
        </li>
      ))}
    </ol>
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
