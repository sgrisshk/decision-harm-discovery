"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

export const SORT_OPTIONS = [
  { value: "exposure", label: "Exposure" },
  { value: "readiness", label: "Readiness" },
  { value: "evidence", label: "Evidence" },
  { value: "recent", label: "Most recently generated" },
] as const;

export const READINESS_FILTER_OPTIONS = [
  { value: "", label: "All" },
  { value: "not_ready", label: "Not ready" },
  { value: "experiment_only", label: "Experiment only" },
  { value: "shadow_policy", label: "Shadow policy" },
  { value: "high_confidence", label: "High confidence" },
] as const;

export const EVIDENCE_FILTER_OPTIONS = [
  { value: "", label: "All" },
  { value: "descriptive_observation", label: "Observed pattern" },
  { value: "predictive_association", label: "Predicts outcome" },
  { value: "adjusted_observational_association", label: "Holds after adjustment" },
  { value: "quasi_causal_evidence", label: "Quasi-causal" },
  { value: "experimental_evidence", label: "Experimentally confirmed" },
] as const;

export const WARNINGS_FILTER_OPTIONS = [
  { value: "", label: "All" },
  { value: "present", label: "With caveats" },
  { value: "absent", label: "No caveats" },
] as const;

/**
 * Plain <select>s that push updated URL search params — the list itself is
 * sorted/filtered/paginated server-side in page.tsx from those params, so
 * this component holds no data, only the controls. Changing any filter or
 * sort resets to page 1 (docs/product/findings-list-screen.md: pagination
 * order must stay stable *within* a page view, not that a filter change
 * should preserve an unrelated page number).
 */
export function FindingsControls() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  function setParam(key: string, value: string) {
    const params = new URLSearchParams(searchParams.toString());
    if (value) {
      params.set(key, value);
    } else {
      params.delete(key);
    }
    params.delete("page");
    router.push(`${pathname}?${params.toString()}`);
  }

  return (
    <div className="findingsControls">
      <label className="findingsControls-field">
        Sort
        <select
          value={searchParams.get("sort") ?? "exposure"}
          onChange={(event) => setParam("sort", event.target.value)}
        >
          {SORT_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <label className="findingsControls-field">
        Readiness
        <select
          value={searchParams.get("readiness") ?? ""}
          onChange={(event) => setParam("readiness", event.target.value)}
        >
          {READINESS_FILTER_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <label className="findingsControls-field">
        Evidence
        <select
          value={searchParams.get("evidence") ?? ""}
          onChange={(event) => setParam("evidence", event.target.value)}
        >
          {EVIDENCE_FILTER_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <label className="findingsControls-field">
        Caveats
        <select
          value={searchParams.get("warnings") ?? ""}
          onChange={(event) => setParam("warnings", event.target.value)}
        >
          {WARNINGS_FILTER_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <Link href="/findings/review" className="findingsControls-reviewLink">
        Start review session
      </Link>
    </div>
  );
}
