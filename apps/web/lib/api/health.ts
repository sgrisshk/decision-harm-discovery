import { apiFetch } from "./client";
import type { HealthStatus } from "./types";

// Mirrors the unversioned operations endpoints in apps/api/app/main.py.
// Used by the dev-only status view; not part of the product surface.

export function getHealth(): Promise<HealthStatus> {
  return apiFetch<HealthStatus>("/health");
}

export function getReadiness(): Promise<HealthStatus> {
  return apiFetch<HealthStatus>("/ready");
}
