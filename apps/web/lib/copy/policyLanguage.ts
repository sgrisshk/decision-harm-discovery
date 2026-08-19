import type { PolicyCandidateStatus } from "@/lib/api/types";

/**
 * Single source of truth for Policy Candidate status wording — mirrors
 * lib/copy/findingLanguage.ts's own role for Finding vocabulary. See
 * docs/product/policy-candidate-domain-model.md §8 for the forward-only state
 * machine these labels describe.
 */
export const POLICY_CANDIDATE_STATUS_LABELS: Record<PolicyCandidateStatus, string> = {
  DRAFT: "Draft",
  UNDER_REVIEW: "Under review",
  REJECTED: "Rejected",
  APPROVED_SHADOW: "Approved (shadow)",
  APPROVED_FOR_CUSTOMER_DECISION: "Proposed for customer decision",
  RETIRED: "Retired",
};
