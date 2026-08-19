"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { EvidencePill } from "@/components/findings/EvidencePill";
import { ExposureFigure } from "@/components/findings/ExposureFigure";
import { ReadinessPill } from "@/components/findings/ReadinessPill";
import { WarningBadge } from "@/components/findings/WarningBadge";
import { listFindings } from "@/lib/api/findings";
import { toErrorDisplay } from "@/lib/api/display";
import type { Finding } from "@/lib/api/types";
import { FindingsControls } from "./FindingsControls";
import { filterFindings, paginateFindings, sortFindings } from "./sortFindings";

type SearchParams = Record<string, string | string[] | undefined>;

function firstValue(value: string | string[] | undefined): string {
  return Array.isArray(value) ? (value[0] ?? "") : (value ?? "");
}

type Result = { attempt: number } & ({ findings: Finding[] } | { error: unknown });

export function FindingsView() {
  const searchParams = useSearchParams();
  const params: SearchParams = Object.fromEntries(searchParams.entries());
  const sort = firstValue(params.sort) || "exposure";
  const readiness = firstValue(params.readiness);
  const evidence = firstValue(params.evidence);
  const warnings = firstValue(params.warnings);
  const requestedPage = Number.parseInt(firstValue(params.page), 10) || 1;

  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<Result | null>(null);

  useEffect(() => {
    let cancelled = false;
    listFindings()
      .then((findings) => {
        if (!cancelled) setResult({ attempt, findings });
      })
      .catch((error: unknown) => {
        if (!cancelled) setResult({ attempt, error });
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const retry = () => setAttempt((current) => current + 1);

  if (result === null || result.attempt !== attempt) {
    return (
      <PageShell count={undefined}>
        <LoadingState label="Loading findings…" />
      </PageShell>
    );
  }

  if ("error" in result) {
    const { message, requestId } = toErrorDisplay(result.error);
    return (
      <PageShell count={undefined}>
        <ErrorState title="Could not load findings" message={message} requestId={requestId} onRetry={retry} />
      </PageShell>
    );
  }

  const { findings } = result;
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
      <Link href={`/findings/detail?id=${finding.id}`} className="findingRow-link">
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
