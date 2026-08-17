import type { ReactNode } from "react";
import { EmptyState, ErrorState } from "@/components/states";
import { toErrorDisplay } from "@/lib/api/display";
import { listFindings } from "@/lib/api/findings";

export const metadata = {
  title: "Findings — Signal Foundry",
};

// See app/(app)/datasets/page.tsx for why this is required: without it,
// `next build` can bake a build-time API result (including a build-time
// failure) into a static page instead of rendering per request.
export const dynamic = "force-dynamic";

export default async function FindingsPage() {
  let findings;
  try {
    findings = await listFindings();
  } catch (error) {
    const { message, requestId } = toErrorDisplay(error);
    return (
      <PageShell>
        <ErrorState
          title="Could not load findings"
          message={message}
          requestId={requestId}
          retryHref="/findings"
        />
      </PageShell>
    );
  }

  return (
    <PageShell>
      {findings.length === 0 ? (
        <EmptyState
          title="No findings yet"
          description="Validated findings will appear here once discovery and statistical validation have run on a dataset."
        />
      ) : (
        <ul className="resourceList">
          {findings.map((finding) => (
            <li className="resourceCard" key={finding.id}>
              <span className="resourceCard-title">{finding.title}</span>
              {/* Evidence-level and lifecycle labels are shown verbatim as the API
                  returns them (packages/schemas EvidenceLevel/FindingLifecycleStatus).
                  Do not rephrase these — evidence wording is Product-owned. */}
              <span className="resourceCard-tag">{finding.evidence_level}</span>
              <span className="resourceCard-tag">{finding.lifecycle_status}</span>
            </li>
          ))}
        </ul>
      )}
    </PageShell>
  );
}

function PageShell({ children }: { children: ReactNode }) {
  return (
    <>
      <div className="appPageHeader">
        <h1>Findings</h1>
        <p>Validated findings, as returned by the API. This is a foundation view — the full evidence/impact detail screen is a separate, not-yet-unblocked piece of work.</p>
      </div>
      {children}
    </>
  );
}
