import { apiFetch } from "./client";
import type { FeedbackCreatePayload, Finding, FindingFeedback } from "./types";

// Mirrors apps/api/app/findings/routes.py.

export function listFindings(datasetId?: string): Promise<Finding[]> {
  const query = datasetId ? `?dataset_id=${encodeURIComponent(datasetId)}` : "";
  return apiFetch<Finding[]>(`/api/v1/findings${query}`);
}

export function getFinding(id: string): Promise<Finding> {
  return apiFetch<Finding>(`/api/v1/findings/${encodeURIComponent(id)}`);
}

export function listFindingFeedback(findingId: string): Promise<FindingFeedback[]> {
  return apiFetch<FindingFeedback[]>(`/api/v1/findings/${encodeURIComponent(findingId)}/feedback`);
}

/** Requires an authenticated session (`TASK-053`) — 401s if nobody is logged in. */
export function submitFindingFeedback(
  findingId: string,
  payload: FeedbackCreatePayload,
): Promise<FindingFeedback> {
  return apiFetch<FindingFeedback>(`/api/v1/findings/${encodeURIComponent(findingId)}/feedback`, {
    method: "POST",
    body: payload,
  });
}
