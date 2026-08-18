import type {
  EvidenceLevel,
  FeedbackActionability,
  FeedbackCertainty,
  FeedbackCommitmentStrength,
  FeedbackNovelty,
  FeedbackTag,
  PolicyReadiness,
} from "@/lib/api/types";

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
 * Feedback-capture labels (`TASK-035`, `docs/product/finding-feedback-contract.md` §2). The six
 * values split into two nullable single-select axes plus a multi-select tag set — see the
 * contract for why these are not one flat enum.
 */
export const FEEDBACK_NOVELTY_LABELS: Record<FeedbackNovelty, string> = {
  KNOWN_ALREADY: "Known already",
  NEW: "New to us",
};

export const FEEDBACK_ACTIONABILITY_LABELS: Record<FeedbackActionability, string> = {
  ACTIONABLE: "Actionable",
  NOT_ACTIONABLE: "Not actionable",
};

export const FEEDBACK_TAG_LABELS: Record<FeedbackTag, string> = {
  WRONG: "Doesn't look right",
  INTERESTING: "Interesting",
};

export const FEEDBACK_CERTAINTY_LABELS: Record<FeedbackCertainty, string> = {
  LOW: "Low",
  MEDIUM: "Medium",
  HIGH: "High",
};

export const FEEDBACK_COMMITMENT_LABELS: Record<FeedbackCommitmentStrength, string> = {
  STATED_COMMITMENT: "Stated commitment",
  STATED_INTENTION: "Stated intention",
  NONE: "None",
};
