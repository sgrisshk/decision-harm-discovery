import { EVIDENCE_LABELS } from "@/lib/copy/findingLanguage";
import type { EvidenceLevel } from "@/lib/api/types";

export function EvidencePill({ level }: { level: EvidenceLevel }) {
  return <span className="pill pill--evidence">{EVIDENCE_LABELS[level]}</span>;
}
