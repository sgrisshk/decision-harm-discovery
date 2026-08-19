import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ReviewSessionView } from "./ReviewSessionView";

const originalFetch = global.fetch;

function finding(id: string, title: string) {
  return {
    id,
    dataset_id: "dataset-1",
    analysis_run_id: "run-1",
    candidate_pattern_id: `cand-${id}`,
    validation_report_id: `report-${id}`,
    title,
    summary: `${title} summary`,
    title_template_version: "v0-mechanical",
    generated_at: "2026-08-17T00:00:00Z",
    pattern: { candidate_key: `CAND-${id}`, conditions: [], fit_split: "development", rank: 1, rank_score: 0.5, actionability: "HIGH" },
    exposed_records: 100,
    comparison_records: 900,
    clustering_key: "customer_id",
    evidence_level: "descriptive_observation" as const,
    identification_design: "observational" as const,
    evidence: {
      raw_effect: { value: 10, ci_low: 5, ci_high: 15, confidence_level: 0.95, method: "m", unit: "EUR" },
      adjusted_effect: null,
      controlled_variables: [],
      potential_confounders: [],
      robustness_tests: [],
      temporal_stability: "",
      warnings: [],
      failure_modes: [],
      recommended_validation: "",
      permitted_language: "descriptive only",
    },
    impact: {
      impact_contract_version: "1.0.0",
      outcome_name: "contribution_margin_eur",
      outcome_unit: "EUR/booking",
      affected_records: 100,
      per_record_effect: { value: 10, ci_low: 5, ci_high: 15, confidence_level: 0.95, method: "m", unit: "EUR" },
      historical_impact: { value: 1000, ci_low: 500, ci_high: 1500, confidence_level: 0.95, method: "m", unit: "EUR" },
      annualized_impact: null,
      annualization_justified: false,
      materiality_pass: true,
    },
    policy_readiness: "shadow_policy" as const,
    lifecycle_status: "ACTIVE" as const,
    created_at: "2026-08-17T00:00:00Z",
    updated_at: "2026-08-17T00:00:00Z",
  };
}

const findingA = finding("finding-a", "Finding A");
const findingB = finding("finding-b", "Finding B");

function mockFetchRouter() {
  return vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    if (url.endsWith("/api/v1/auth/me")) {
      return Promise.resolve(
        new Response(JSON.stringify({ id: "u1", email: "r@example.com", display_name: "R" }), {
          status: 200,
        }),
      );
    }
    if (url.endsWith("/api/v1/findings") && method === "GET") {
      return Promise.resolve(new Response(JSON.stringify([findingA, findingB]), { status: 200 }));
    }
    if (url.includes("/feedback") && method === "POST") {
      return Promise.resolve(new Response(JSON.stringify({ id: "fb-1" }), { status: 201 }));
    }
    return Promise.resolve(new Response("not found", { status: 404 }));
  });
}

beforeEach(() => {
  vi.stubEnv("NEXT_PUBLIC_API_URL", "http://api.test");
  window.localStorage.clear();
});

afterEach(() => {
  global.fetch = originalFetch;
  vi.unstubAllEnvs();
  window.localStorage.clear();
});

describe("ReviewSessionView", () => {
  it("requires login when nobody is authenticated", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "Not authenticated" }), { status: 401 }),
    );
    render(<ReviewSessionView />);
    expect(await screen.findByText("Log in to start a review session")).toBeInTheDocument();
  });

  it("walks a full session: save one, skip one, reach the completion screen", async () => {
    global.fetch = mockFetchRouter();
    render(<ReviewSessionView />);

    fireEvent.change(await screen.findByLabelText(/Review session/), {
      target: { value: "acme-2026-08-19" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Start session" }));

    expect(await screen.findByText("Finding A")).toBeInTheDocument();
    expect(screen.getByText("Finding 1 of 2")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Save and next" }));

    expect(await screen.findByText("Finding B")).toBeInTheDocument();
    expect(screen.getByText("Finding 2 of 2")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Skip" }));

    expect(await screen.findByText("Session complete")).toBeInTheDocument();
    expect(screen.getByText("1 reviewed, 1 skipped this session.")).toBeInTheDocument();
  });

  it("shows an empty state when everything was already handled this session", async () => {
    window.localStorage.setItem(
      "sf-review-session:acme-2026-08-19",
      JSON.stringify({ savedIds: ["finding-a"], skippedIds: ["finding-b"] }),
    );
    global.fetch = mockFetchRouter();
    render(<ReviewSessionView />);

    fireEvent.change(await screen.findByLabelText(/Review session/), {
      target: { value: "acme-2026-08-19" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Start session" }));

    await waitFor(() =>
      expect(screen.getByText("No findings left to review in this session.")).toBeInTheDocument(),
    );
  });
});
