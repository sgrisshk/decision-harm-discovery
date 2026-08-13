import { apiFetch } from "./client";
import type { Finding } from "./types";

// Mirrors apps/api/app/findings/routes.py.

export function listFindings(datasetId?: string): Promise<Finding[]> {
  const query = datasetId ? `?dataset_id=${encodeURIComponent(datasetId)}` : "";
  return apiFetch<Finding[]>(`/api/v1/findings${query}`);
}

export function getFinding(id: string): Promise<Finding> {
  return apiFetch<Finding>(`/api/v1/findings/${encodeURIComponent(id)}`);
}
