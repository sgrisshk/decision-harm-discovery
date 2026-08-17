import type { EvidenceLevel, PolicyReadiness } from "@/lib/api/types";

/**
 * Single source of truth for the evidence/readiness pill wording. Both
 * docs/product/findings-list-screen.md and docs/product/finding-detail-screen.md
 * require identical labels on both screens ("a user must not learn two
 * vocabularies for the same concept") — `EvidencePill`/`ReadinessPill` are the
 * only components that read from here, so the two screens cannot diverge.
 */
export const EVIDENCE_LABELS: Record<EvidenceLevel, string> = {
  descriptive_observation: "Observed pattern",
  predictive_association: "Predicts outcome",
  adjusted_observational_association: "Holds after adjustment",
  quasi_causal_evidence: "Quasi-causal",
  experimental_evidence: "Experimentally confirmed",
};

export const READINESS_LABELS: Record<PolicyReadiness, string> = {
  not_ready: "Not ready",
  experiment_only: "Experiment only",
  shadow_policy: "Shadow policy",
  high_confidence: "High confidence",
};

/**
 * docs/product/finding-product-contract.md §3: "savings"/"recoverable" language is
 * forbidden at evidence levels 1-3, and at 4-5 without a positive backtest.
 * No finding on this dataset can exceed adjusted_observational_association (level 3)
 * and no backtest (TASK-032) exists, so this is deterministically always "exposure"
 * today — a constant with a reason, not a dead branch pretending otherwise. Takes no
 * argument on purpose: nothing today varies the answer, and a parameter that can
 * never produce a different result would be a false promise of future behavior.
 * When TASK-032 (backtesting) exists, re-add an EvidenceLevel parameter here.
 */
export function impactFramingLabel(): "exposure" {
  return "exposure";
}

/**
 * Reaction options for the feedback-capture UI slot (docs/product/finding-detail-screen.md
 * §7, entry point for TASK-035/036). The full semantic contract lives in
 * docs/product/finding-feedback-contract.md; this screen only reserves the slot.
 */
export const FEEDBACK_REACTIONS = [
  "Known already",
  "New to us",
  "Doesn't look right",
  "Not actionable",
  "Interesting",
  "Actionable",
] as const;
