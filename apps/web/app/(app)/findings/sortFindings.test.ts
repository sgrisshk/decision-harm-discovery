import { describe, expect, it } from "vitest";
import type { EffectEstimate, Finding } from "@/lib/api/types";
import { PAGE_SIZE, filterFindings, paginateFindings, sortFindings } from "./sortFindings";

function estimate(overrides: Partial<EffectEstimate> = {}): EffectEstimate {
  return {
    value: 100,
    ci_low: 100,
    ci_high: 100,
    confidence_level: 0.95,
    method: "test",
    unit: "EUR",
    ...overrides,
  };
}

function finding(overrides: Partial<Finding> = {}): Finding {
  return {
    id: crypto.randomUUID(),
    dataset_id: "dataset",
    analysis_run_id: "run",
    candidate_pattern_id: "candidate",
    validation_report_id: "report",
    title: "Test finding",
    summary: "Test finding summary.",
    title_template_version: "v0-mechanical",
    generated_at: "2026-08-17T00:00:00Z",
    pattern: {
      candidate_key: "CAND-TEST",
      conditions: [],
      fit_split: "development",
      rank: 1,
      rank_score: 0.5,
      actionability: "HIGH",
    },
    exposed_records: 100,
    comparison_records: 900,
    clustering_key: "customer_id",
    evidence_level: "descriptive_observation",
    identification_design: "observational",
    evidence: {
      raw_effect: estimate(),
      adjusted_effect: null,
      controlled_variables: [],
      potential_confounders: [],
      robustness_tests: [],
      temporal_stability: "",
      warnings: [],
      failure_modes: [],
      recommended_validation: "",
      permitted_language: "",
    },
    impact: {
      impact_contract_version: "1.0.0",
      outcome_name: "contribution_margin_eur",
      outcome_unit: "EUR",
      affected_records: 100,
      per_record_effect: estimate(),
      historical_impact: estimate({ ci_low: 1000, ci_high: 2000 }),
      annualized_impact: null,
      annualization_justified: false,
      materiality_pass: true,
    },
    policy_readiness: "not_ready",
    lifecycle_status: "ACTIVE",
    created_at: "2026-08-17T00:00:00Z",
    updated_at: "2026-08-17T00:00:00Z",
    ...overrides,
  };
}

describe("sortFindings", () => {
  it("default (exposure) sorts descending by historical_impact.ci_low", () => {
    const low = finding({ id: "low", impact: { ...finding().impact, historical_impact: estimate({ ci_low: 100, ci_high: 200 }) } });
    const high = finding({ id: "high", impact: { ...finding().impact, historical_impact: estimate({ ci_low: 900, ci_high: 1200 }) } });
    const sorted = sortFindings([low, high], "exposure");
    expect(sorted.map((f) => f.id)).toEqual(["high", "low"]);
  });

  it("exposure sort places non-material findings (ci_low <= 0) after material ones, never dropped", () => {
    const material = finding({ id: "material", impact: { ...finding().impact, historical_impact: estimate({ ci_low: 100, ci_high: 200 }) } });
    const nonMaterial = finding({ id: "non-material", impact: { ...finding().impact, historical_impact: estimate({ ci_low: -10, ci_high: 200 }) } });
    const sorted = sortFindings([nonMaterial, material], "exposure");
    expect(sorted.map((f) => f.id)).toEqual(["material", "non-material"]);
    expect(sorted).toHaveLength(2);
  });

  it("sorts by readiness rank, most actionable first", () => {
    const notReady = finding({ id: "not-ready", policy_readiness: "not_ready" });
    const shadow = finding({ id: "shadow", policy_readiness: "shadow_policy" });
    const experiment = finding({ id: "experiment", policy_readiness: "experiment_only" });
    const sorted = sortFindings([notReady, experiment, shadow], "readiness");
    expect(sorted.map((f) => f.id)).toEqual(["shadow", "experiment", "not-ready"]);
  });

  it("sorts by evidence level, strongest first", () => {
    const descriptive = finding({ id: "descriptive", evidence_level: "descriptive_observation" });
    const adjusted = finding({ id: "adjusted", evidence_level: "adjusted_observational_association" });
    const sorted = sortFindings([descriptive, adjusted], "evidence");
    expect(sorted.map((f) => f.id)).toEqual(["adjusted", "descriptive"]);
  });

  it("sorts by most recently generated", () => {
    const older = finding({ id: "older", generated_at: "2026-08-01T00:00:00Z" });
    const newer = finding({ id: "newer", generated_at: "2026-08-17T00:00:00Z" });
    const sorted = sortFindings([older, newer], "recent");
    expect(sorted.map((f) => f.id)).toEqual(["newer", "older"]);
  });
});

describe("filterFindings", () => {
  it("filters by readiness", () => {
    const shadow = finding({ id: "shadow", policy_readiness: "shadow_policy" });
    const notReady = finding({ id: "not-ready", policy_readiness: "not_ready" });
    const filtered = filterFindings([shadow, notReady], { readiness: "shadow_policy" });
    expect(filtered.map((f) => f.id)).toEqual(["shadow"]);
  });

  it("filters by evidence level", () => {
    const a = finding({ id: "a", evidence_level: "descriptive_observation" });
    const b = finding({ id: "b", evidence_level: "adjusted_observational_association" });
    const filtered = filterFindings([a, b], { evidence: "adjusted_observational_association" });
    expect(filtered.map((f) => f.id)).toEqual(["b"]);
  });

  it("filters by warnings present/absent", () => {
    const withWarning = finding({ id: "with", evidence: { ...finding().evidence, warnings: ["G12 fail"] } });
    const without = finding({ id: "without" });
    expect(filterFindings([withWarning, without], { warnings: "present" }).map((f) => f.id)).toEqual(["with"]);
    expect(filterFindings([withWarning, without], { warnings: "absent" }).map((f) => f.id)).toEqual(["without"]);
  });

  it("does not filter by materiality — immaterial findings must still be visible", () => {
    const notReady = finding({ id: "not-ready", policy_readiness: "not_ready" });
    const filtered = filterFindings([notReady], {});
    expect(filtered).toHaveLength(1);
  });
});

describe("paginateFindings", () => {
  it("returns all items on one page when under the page size", () => {
    const items = Array.from({ length: 5 }, (_, i) => finding({ id: `f${i}` }));
    const result = paginateFindings(items, 1);
    expect(result.items).toHaveLength(5);
    expect(result.totalPages).toBe(1);
  });

  it("splits into pages and clamps an out-of-range page number", () => {
    const items = Array.from({ length: PAGE_SIZE + 5 }, (_, i) => finding({ id: `f${i}` }));
    const result = paginateFindings(items, 99);
    expect(result.totalPages).toBe(2);
    expect(result.page).toBe(2);
    expect(result.items).toHaveLength(5);
  });

  it("clamps page numbers below 1", () => {
    const items = [finding()];
    const result = paginateFindings(items, 0);
    expect(result.page).toBe(1);
  });
});
