import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TriggerBacktestForm } from "./TriggerBacktestForm";
import type { PolicyBacktestRun } from "@/lib/api/types";

const originalFetch = global.fetch;

beforeEach(() => {
  vi.stubEnv("NEXT_PUBLIC_API_URL", "http://api.test");
});

afterEach(() => {
  global.fetch = originalFetch;
  vi.unstubAllEnvs();
});

function completedRun(overrides: Partial<PolicyBacktestRun> = {}): PolicyBacktestRun {
  return {
    id: "run-1",
    policy_candidate_id: "cand-1",
    cost_per_review_eur: null,
    status: "completed",
    created_at: "2026-08-19T00:00:00Z",
    failure_reason: null,
    backtest_result: {
      backtest_contract_version: "1.0.0",
      outcome_name: "contribution_margin_eur",
      outcome_unit: "EUR per booking",
      window: "future_holdout",
      affected_decisions: 570,
      avoided_bad_outcomes: 108,
      suppressed_good_outcomes: 462,
      bad_outcome_definition: "contribution_margin_eur < 0.0",
      benefit: {
        value: 154454.9,
        ci_low: 122373.1,
        ci_high: 188717.13,
        confidence_level: 0.95,
        method: "cluster_bootstrap",
        unit: "EUR per booking",
      },
      benefit_is_adjusted: false,
      operational_cost_per_review_eur: null,
      operational_cost: null,
      net_effect: {
        value: 154454.9,
        ci_low: 122373.1,
        ci_high: 188717.13,
        confidence_level: 0.95,
        method: "cluster_bootstrap",
        unit: "EUR per booking",
      },
      net_effect_is_cost_exclusive: true,
      no_measurable_net_effect: false,
      methodology_disclosure: "Mechanical replay against future_holdout, not a forecast.",
    },
    ...overrides,
  };
}

describe("TriggerBacktestForm", () => {
  it("shows an empty state when no run exists yet", () => {
    render(<TriggerBacktestForm candidateId="cand-1" initialRuns={[]} />);
    expect(screen.getByText("No backtest has been run yet.")).toBeInTheDocument();
  });

  it("renders an existing completed run's result", () => {
    render(<TriggerBacktestForm candidateId="cand-1" initialRuns={[completedRun()]} />);
    expect(screen.getByText(/570 bookings/)).toBeInTheDocument();
    expect(screen.getByText(/108 bookings/)).toBeInTheDocument();
  });

  it("triggers a new run and renders its result", async () => {
    global.fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(completedRun()), { status: 200 }));
    render(<TriggerBacktestForm candidateId="cand-1" initialRuns={[]} />);

    fireEvent.click(screen.getByRole("button", { name: "Run historical backtest" }));

    expect(await screen.findByText(/570 bookings/)).toBeInTheDocument();
    expect(global.fetch).toHaveBeenCalledWith(
      "http://api.test/api/v1/policy-candidates/cand-1/backtest",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("shows the failure reason for a failed run", () => {
    const failed = completedRun({
      status: "failed",
      backtest_result: null,
      failure_reason: "future_holdout has no exposed records for this condition",
    });
    render(<TriggerBacktestForm candidateId="cand-1" initialRuns={[failed]} />);
    expect(
      screen.getByText("future_holdout has no exposed records for this condition"),
    ).toBeInTheDocument();
  });

  it("offers 'propose for customer decision' only when net effect is positive", () => {
    render(<TriggerBacktestForm candidateId="cand-1" initialRuns={[completedRun()]} />);
    expect(
      screen.getByRole("button", { name: "Propose for customer decision" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Retire this candidate" }),
    ).not.toBeInTheDocument();
  });
});
