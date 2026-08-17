import { READINESS_LABELS } from "@/lib/copy/findingLanguage";
import type { PolicyReadiness } from "@/lib/api/types";

export function ReadinessPill({ readiness }: { readiness: PolicyReadiness }) {
  return (
    <span className={`pill pill--readiness pill--readiness-${readiness}`}>
      {READINESS_LABELS[readiness]}
    </span>
  );
}
