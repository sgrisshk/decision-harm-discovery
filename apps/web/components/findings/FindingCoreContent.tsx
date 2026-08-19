import type { ReactNode } from "react";
import { ExposureFigure } from "@/components/findings/ExposureFigure";
import { EVIDENCE_LABELS } from "@/lib/copy/findingLanguage";
import type { EvidenceLevel, Finding } from "@/lib/api/types";

const EVIDENCE_LADDER: EvidenceLevel[] = [
  "descriptive_observation",
  "predictive_association",
  "adjusted_observational_association",
  "quasi_causal_evidence",
  "experimental_evidence",
];

/**
 * §1-§6 of `docs/product/finding-detail-screen.md` — what we found, who it applies to, money at
 * stake, evidence strength, alternative explanations, warnings. Extracted from
 * `FindingDetailView.tsx` (`TASK-036`) so `docs/product/customer-review-workflow.md` §2's "reusing
 * the detail screen's core content, not a re-summarized version" is literally true: both views
 * render the same component, not two copies that can drift apart.
 */
export function FindingCoreContent({ finding }: { finding: Finding }) {
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
            Annualized estimate: <ExposureFigure estimate={finding.impact.annualized_impact} />
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
    </>
  );
}

export function Section({
  number,
  title,
  children,
}: {
  number: number;
  title: string;
  children: ReactNode;
}) {
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
