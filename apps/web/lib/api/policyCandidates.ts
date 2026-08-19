import { apiFetch } from "./client";
import type {
  PolicyBacktestRun,
  PolicyCandidate,
  PolicyCandidateTransitionPayload,
} from "./types";

// Mirrors apps/api/app/policies/routes.py.

export function listPolicyCandidates(findingId: string): Promise<PolicyCandidate[]> {
  return apiFetch<PolicyCandidate[]>(
    `/api/v1/policy-candidates?finding_id=${encodeURIComponent(findingId)}`,
  );
}

export function getPolicyCandidate(id: string): Promise<PolicyCandidate> {
  return apiFetch<PolicyCandidate>(`/api/v1/policy-candidates/${encodeURIComponent(id)}`);
}

export function transitionPolicyCandidate(
  id: string,
  payload: PolicyCandidateTransitionPayload,
): Promise<PolicyCandidate> {
  return apiFetch<PolicyCandidate>(
    `/api/v1/policy-candidates/${encodeURIComponent(id)}/transition`,
    { method: "POST", body: payload },
  );
}

export function triggerBacktest(
  id: string,
  costPerReviewEur: number | null,
): Promise<PolicyBacktestRun> {
  return apiFetch<PolicyBacktestRun>(
    `/api/v1/policy-candidates/${encodeURIComponent(id)}/backtest`,
    { method: "POST", body: { cost_per_review_eur: costPerReviewEur } },
  );
}

export function listBacktestRuns(id: string): Promise<PolicyBacktestRun[]> {
  return apiFetch<PolicyBacktestRun[]>(
    `/api/v1/policy-candidates/${encodeURIComponent(id)}/backtest`,
  );
}
