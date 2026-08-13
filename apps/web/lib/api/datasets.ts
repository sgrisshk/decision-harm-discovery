import { apiFetch } from "./client";
import type { Dataset } from "./types";

// Mirrors apps/api/app/datasets/routes.py. Only the read operations this
// shell's pages need are wired up; POST /api/v1/datasets exists on the
// backend but has no approved upload UX yet, so it is intentionally not
// exposed here (see apps/web/lib/api/README.md).

export function listDatasets(): Promise<Dataset[]> {
  return apiFetch<Dataset[]>("/api/v1/datasets");
}

export function getDataset(id: string): Promise<Dataset> {
  return apiFetch<Dataset>(`/api/v1/datasets/${encodeURIComponent(id)}`);
}
