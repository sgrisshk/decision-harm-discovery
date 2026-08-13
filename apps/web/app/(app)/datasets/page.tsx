import type { ReactNode } from "react";
import { EmptyState, ErrorState } from "@/components/states";
import { listDatasets } from "@/lib/api/datasets";
import { toErrorDisplay } from "@/lib/api/display";

export const metadata = {
  title: "Datasets — Signal Foundry",
};

// This page must reflect live backend state on every request, not whatever
// the API returned (or failed to return) at build time. `apiFetch` already
// passes `cache: "no-store"`, but that only affects fetch-level caching;
// without this, Next can still prerender the whole route to a static shell
// at build time (observed: `next build` produced a static /datasets page
// baked from a build-time API error). `force-dynamic` makes the App Router
// render this route per request instead.
export const dynamic = "force-dynamic";

export default async function DatasetsPage() {
  let datasets;
  try {
    datasets = await listDatasets();
  } catch (error) {
    const { message, requestId } = toErrorDisplay(error);
    return (
      <PageShell>
        <ErrorState
          title="Could not load datasets"
          message={message}
          requestId={requestId}
          retryHref="/datasets"
        />
      </PageShell>
    );
  }

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
