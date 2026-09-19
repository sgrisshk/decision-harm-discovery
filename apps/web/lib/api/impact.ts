import type { CandidateExposureTier, FindingImpact } from "./types";

/**
 * `FindingImpactRead.tier1`/`tier2` being non-null does NOT mean either may be
 * rendered — only a tier number appearing in `reportable_tiers` does
 * (`TASK-088`/`TASK-090`): `reportable_tiers` names which tiers this specific
 * Finding's own evidence level actually cleared for display. These two
 * accessors are the single place that rule is enforced, so every caller
 * (sorting, list rows, detail views) reads the same reportability decision
 * instead of re-deriving it and risking drift.
 */
export function reportableTier1(impact: FindingImpact): CandidateExposureTier | null {
  return impact.tier1 && impact.reportable_tiers.includes(1) ? impact.tier1 : null;
}

export function reportableTier2(impact: FindingImpact): CandidateExposureTier | null {
  return impact.tier2 && impact.reportable_tiers.includes(2) ? impact.tier2 : null;
}

/**
 * The single "money at stake" headline number, when this Finding's evidence
 * level clears it: tier 1's own `candidate_exposure.ci_low` (population `E`,
 * the full historical window) — the conservative lower bound, never the
 * point estimate, matching `docs/product/findings-list-screen.md`'s sort
 * rule. `null` when tier 1 is not reportable, meaning "no usable headline
 * figure" rather than "zero" — callers must not conflate the two.
 */
export function headlineExposureCiLow(impact: FindingImpact): number | null {
  return reportableTier1(impact)?.candidate_exposure.ci_low ?? null;
}
