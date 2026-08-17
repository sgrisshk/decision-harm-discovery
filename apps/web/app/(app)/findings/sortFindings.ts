import type { Finding } from "@/lib/api/types";

const READINESS_RANK: Record<Finding["policy_readiness"], number> = {
  high_confidence: 4,
  shadow_policy: 3,
  experiment_only: 2,
  not_ready: 1,
};

const EVIDENCE_RANK: Record<Finding["evidence_level"], number> = {
  experimental_evidence: 5,
  quasi_causal_evidence: 4,
  adjusted_observational_association: 3,
  predictive_association: 2,
  descriptive_observation: 1,
};

/**
 * Default sort ("exposure"): descending by impact.historical_impact.ci_low — the
 * conservative lower bound, not the point estimate, per
 * docs/product/findings-list-screen.md's sort rule. Findings whose interval does
 * not exclude zero (no usable ci_low to rank by) sort after every material
 * finding but keep their relative order among themselves — the spec's only fixed
 * requirement for them is that they must still appear, never be dropped.
 */
export function sortFindings(findings: Finding[], sort: string): Finding[] {
  const copy = [...findings];
  switch (sort) {
    case "readiness":
      return copy.sort(
        (a, b) => READINESS_RANK[b.policy_readiness] - READINESS_RANK[a.policy_readiness]
      );
    case "evidence":
      return copy.sort(
        (a, b) => EVIDENCE_RANK[b.evidence_level] - EVIDENCE_RANK[a.evidence_level]
      );
    case "recent":
      return copy.sort(
        (a, b) => new Date(b.generated_at).getTime() - new Date(a.generated_at).getTime()
      );
    case "exposure":
    default:
      return copy.sort((a, b) => {
        const aMaterial = a.impact.historical_impact.ci_low > 0;
        const bMaterial = b.impact.historical_impact.ci_low > 0;
        if (aMaterial !== bMaterial) {
          return aMaterial ? -1 : 1;
        }
        if (!aMaterial) {
          return 0;
        }
        return b.impact.historical_impact.ci_low - a.impact.historical_impact.ci_low;
      });
  }
}

export type FindingsFilters = {
  readiness?: string;
  evidence?: string;
  warnings?: string;
};

/**
 * Materiality (policy_readiness === "not_ready" from an immaterial gate) never
 * gates default visibility — that's enforced upstream (only ACTIVE lifecycle
 * status is excluded, by the API itself). These are opt-in user filters only.
 */
export function filterFindings(findings: Finding[], filters: FindingsFilters): Finding[] {
  return findings.filter((finding) => {
    if (filters.readiness && finding.policy_readiness !== filters.readiness) {
      return false;
    }
    if (filters.evidence && finding.evidence_level !== filters.evidence) {
      return false;
    }
    if (filters.warnings === "present" && finding.evidence.warnings.length === 0) {
      return false;
    }
    if (filters.warnings === "absent" && finding.evidence.warnings.length > 0) {
      return false;
    }
    return true;
  });
}

/**
 * v0 pagination: the API returns all ACTIVE findings in one call (15 today),
 * so paging happens here rather than as a backend cursor — see the plan's
 * "Key implementation decisions" for why. Page size comfortably covers the
 * current data volume; a real cursor is future work once volume demands it.
 */
export const PAGE_SIZE = 20;

export function paginateFindings(
  findings: Finding[],
  page: number
): { items: Finding[]; totalPages: number; page: number } {
  const totalPages = Math.max(1, Math.ceil(findings.length / PAGE_SIZE));
  const clampedPage = Math.min(Math.max(1, page), totalPages);
  const start = (clampedPage - 1) * PAGE_SIZE;
  return { items: findings.slice(start, start + PAGE_SIZE), totalPages, page: clampedPage };
}
