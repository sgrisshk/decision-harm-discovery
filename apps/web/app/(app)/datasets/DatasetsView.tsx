"use client";

import { useEffect, useState, type ReactNode } from "react";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { ApiError } from "@/lib/api/errors";
import { listDatasets } from "@/lib/api/datasets";
import { toErrorDisplay } from "@/lib/api/display";
import type { Dataset } from "@/lib/api/types";

type Result = { attempt: number } & ({ datasets: Dataset[] } | { error: unknown });

export function DatasetsView() {
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<Result | null>(null);

  useEffect(() => {
    let cancelled = false;
    listDatasets()
      .then((datasets) => {
        if (!cancelled) setResult({ attempt, datasets });
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
      <PageShell>
        <LoadingState label="Loading datasets…" />
      </PageShell>
    );
  }

  if ("error" in result) {
    // GET /api/v1/datasets requires authentication (TASK-037 Code Reviewer finding 1 — dataset
    // reads carry literal source-data examples). A generic error state would be misleading here;
    // an anonymous viewer just needs to log in, same as the review-session flow.
    if (result.error instanceof ApiError && result.error.status === 401) {
      return (
        <PageShell>
          <ErrorState
            title="Log in to view datasets"
            message="Dataset details include profiled sample values from the source data, so this view requires an identified reviewer."
            retryHref="/login?next=%2Fdatasets"
          />
        </PageShell>
      );
    }
    const { message, requestId } = toErrorDisplay(result.error);
    return (
      <PageShell>
        <ErrorState title="Could not load datasets" message={message} requestId={requestId} onRetry={retry} />
      </PageShell>
    );
  }

  const { datasets } = result;

  return (
    <PageShell>
      {datasets.length === 0 ? (
        <EmptyState
          title="No datasets yet"
          description="Datasets registered through the API will appear here once uploaded."
        />
      ) : (
        <ul className="resourceList">
          {datasets.map((dataset) => (
            <li className="resourceCard" key={dataset.id}>
              <span className="resourceCard-title">{dataset.name}</span>
              <span className="resourceCard-tag">v{dataset.version}</span>
              <span className="resourceCard-tag">{dataset.status}</span>
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
        <h1>Datasets</h1>
        <p>Registered source datasets. This is a foundation view — upload, profiling, and quality-report surfaces are not implemented yet.</p>
      </div>
      {children}
    </>
  );
}
