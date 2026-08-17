import Link from "next/link";
import type { ReactNode } from "react";
import { EmptyState, ErrorState } from "@/components/states";
import { EvidencePill } from "@/components/findings/EvidencePill";
import { ExposureFigure } from "@/components/findings/ExposureFigure";
import { ReadinessPill } from "@/components/findings/ReadinessPill";
import { WarningBadge } from "@/components/findings/WarningBadge";
import { listFindings } from "@/lib/api/findings";
import { toErrorDisplay } from "@/lib/api/display";
import type { Finding } from "@/lib/api/types";
import { FindingsControls } from "./FindingsControls";
import { filterFindings, paginateFindings, sortFindings } from "./sortFindings";

export const metadata = {
  title: "Findings — Signal Foundry",
};

// See app/(app)/datasets/page.tsx for why this is required: without it,
// `next build` can bake a build-time API result (including a build-time
// failure) into a static page instead of rendering per request.
export const dynamic = "force-dynamic";

type SearchParams = Record<string, string | string[] | undefined>;

function firstValue(value: string | string[] | undefined): string {
  return Array.isArray(value) ? (value[0] ?? "") : (value ?? "");
}

export default async function FindingsPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  const sort = firstValue(params.sort) || "exposure";
  const readiness = firstValue(params.readiness);
  const evidence = firstValue(params.evidence);
  const warnings = firstValue(params.warnings);
  const requestedPage = Number.parseInt(firstValue(params.page), 10) || 1;

  let findings: Finding[];
  try {
    findings = await listFindings();
  } catch (error) {
    const { message, requestId } = toErrorDisplay(error);
    return (
      <PageShell count={undefined}>
        <ErrorState
          title="Could not load findings"
          message={message}
          requestId={requestId}
          retryHref="/findings"
        />
      </PageShell>
    );
  }

  const filtered = filterFindings(findings, { readiness, evidence, warnings });
  const sorted = sortFindings(filtered, sort);
  const { items, totalPages, page } = paginateFindings(sorted, requestedPage);

  return (
    <PageShell count={filtered.length}>
      <FindingsControls />
      {findings.length === 0 ? (
        <EmptyState
          title="No validated findings yet"
          description="Discovered patterns are still going through statistical validation before they're shown here."
        />
      ) : filtered.length === 0 ? (
        <EmptyState
          title="No findings match these filters"
          description="Try clearing a filter — nothing was excluded from the underlying data, only from this view."
        />
      ) : (
        <>
          <ul className="resourceList">
            {items.map((finding) => (
              <FindingRow key={finding.id} finding={finding} />
            ))}
          </ul>
          {totalPages > 1 && (
            <PaginationControls page={page} totalPages={totalPages} searchParams={params} />
          )}
        </>
      )}
    </PageShell>
  );
}

function FindingRow({ finding }: { finding: Finding }) {
  return (
    <li className="resourceCard findingRow">
      <Link href={`/findings/${finding.id}`} className="findingRow-link">
        <span className="findingRow-title">{finding.title}</span>
        <span className="findingRow-pills">
          <EvidencePill level={finding.evidence_level} />
          <ReadinessPill readiness={finding.policy_readiness} />
          <WarningBadge count={finding.evidence.warnings.length} />
        </span>
        <span className="findingRow-figures">
          <ExposureFigure estimate={finding.impact.historical_impact} />
          <span className="findingRow-population">
            {finding.impact.affected_records.toLocaleString("en-US")} bookings affected
          </span>
        </span>
        <span className="findingRow-meta">
          Generated {new Date(finding.generated_at).toLocaleDateString("en-US")}
        </span>
      </Link>
    </li>
  );
}

function PaginationControls({
  page,
  totalPages,
  searchParams,
}: {
  page: number;
  totalPages: number;
  searchParams: SearchParams;
}) {
  function hrefForPage(targetPage: number): string {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(searchParams)) {
      if (key !== "page" && value) {
        params.set(key, firstValue(value));
      }
    }
    params.set("page", String(targetPage));
    return `/findings?${params.toString()}`;
  }

  return (
    <nav className="findingsPagination" aria-label="Findings pages">
      {page > 1 ? (
        <Link href={hrefForPage(page - 1)}>← Previous</Link>
      ) : (
        <span className="findingsPagination-disabled">← Previous</span>
      )}
      <span className="findingsPagination-current">
        Page {page} of {totalPages}
      </span>
      {page < totalPages ? (
        <Link href={hrefForPage(page + 1)}>Next →</Link>
      ) : (
        <span className="findingsPagination-disabled">Next →</span>
      )}
    </nav>
  );
}

function PageShell({ count, children }: { count: number | undefined; children: ReactNode }) {
  return (
    <>
      <div className="appPageHeader">
        <h1>Findings</h1>
        <p>
          {count === undefined
            ? "Validated findings, as returned by the API."
            : `${count} validated finding${count === 1 ? "" : "s"}.`}
        </p>
      </div>
      {children}
    </>
  );
}
