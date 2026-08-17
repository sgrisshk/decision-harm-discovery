import { apiFetch } from "./client";
import type { AnalysisRun } from "./types";

// Mirrors apps/api/app/analysis_runs/routes.py. Only the read used by the
// finding detail screen's provenance strip is wired up here — write access
// (POST) has no approved UI yet, same posture as apps/web/lib/api/datasets.ts.

export function getAnalysisRun(id: string): Promise<AnalysisRun> {
  return apiFetch<AnalysisRun>(`/api/v1/analysis-runs/${encodeURIComponent(id)}`);
}
