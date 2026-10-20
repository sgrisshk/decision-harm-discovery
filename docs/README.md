# Documentation map

Scoped documents live under `docs/`, grouped by domain. Each result document in `docs/benchmark/`
and `docs/analytics/` sits next to the scripts and raw outputs that produced it (`*-evidence/` or `*-raw.json`).

| Directory | Content |
|---|---|
| `docs/architecture/` | Persistence and component contracts |
| `docs/analytics/` | Outcome, discovery, validation, impact and statistical methodology |
| `docs/benchmark/` | Benchmark protocols, pre-registrations, results and their evidence |
| `docs/product/` | Finding and policy contracts, screen behaviour |
| `docs/operations/` | Deployment and operations |
| `docs/security/` | Security reviews |

## Index

### Architecture

- [`canonical-schema-contract.md`](architecture/canonical-schema-contract.md)
- [`dataset-deletion-contract.md`](architecture/dataset-deletion-contract.md)
- [`finding-persistence-contract.md`](architecture/finding-persistence-contract.md)
- [`ingestion-contract.md`](architecture/ingestion-contract.md)

### Analytics

- [`baseline-statistics-v1.md`](analytics/baseline-statistics-v1.md)
- [`candidate-ranking-v0.md`](analytics/candidate-ranking-v0.md)
- [`discovery-design.md`](analytics/discovery-design.md)
- [`discovery-engine-v0.md`](analytics/discovery-engine-v0.md)
- [`economic-impact-contract.md`](analytics/economic-impact-contract.md)
- [`outcome-contract.md`](analytics/outcome-contract.md)
- [`policy-backtest-contract.md`](analytics/policy-backtest-contract.md)
- [`task-080-candidate-composition-safety-design.md`](analytics/task-080-candidate-composition-safety-design.md)
- [`task-085-economic-impact-target-population-semantics.md`](analytics/task-085-economic-impact-target-population-semantics.md)
- [`task-087-economic-impact-calibration-metric-design.md`](analytics/task-087-economic-impact-calibration-metric-design.md)
- [`task-095-k1-reservation-design.md`](analytics/task-095-k1-reservation-design.md)
- [`task-101-max-support-search-eligibility-fix.md`](analytics/task-101-max-support-search-eligibility-fix.md)
- [`task-105-2b-contract-freeze.md`](analytics/task-105-2b-contract-freeze.md)
- [`task-105-g17-design-correction-and-falsification-plan.md`](analytics/task-105-g17-design-correction-and-falsification-plan.md)
- [`task-105-k1-confounding-protection-design.md`](analytics/task-105-k1-confounding-protection-design.md)
- [`validation-contract.md`](analytics/validation-contract.md)

### Benchmark

- [`blind-benchmark-protocol.md`](benchmark/blind-benchmark-protocol.md)
- [`decision-gate.md`](benchmark/decision-gate.md)
- [`difficulty-presets.md`](benchmark/difficulty-presets.md)
- [`multi-domain-benchmarks.md`](benchmark/multi-domain-benchmarks.md)
- [`real-data-decision-gate.md`](benchmark/real-data-decision-gate.md)
- [`simulation-report.md`](benchmark/simulation-report.md)
- [`task-029-benchmark-report-v1.md`](benchmark/task-029-benchmark-report-v1.md)
- [`task-033-backtest-validation-v1.md`](benchmark/task-033-backtest-validation-v1.md)
- [`task-065-b2b-portability-postmortem.md`](benchmark/task-065-b2b-portability-postmortem.md)
- [`task-065-b2b-portability-report.md`](benchmark/task-065-b2b-portability-report.md)
- [`task-067-g06-diagnostic.md`](benchmark/task-067-g06-diagnostic.md)
- [`task-068-ecommerce-preregistration.md`](benchmark/task-068-ecommerce-preregistration.md)
- [`task-069-g12-form-investigation.md`](benchmark/task-069-g12-form-investigation.md)
- [`task-069-oracle-decomposition.md`](benchmark/task-069-oracle-decomposition.md)
- [`task-069-validation-power-autopsy.md`](benchmark/task-069-validation-power-autopsy.md)
- [`task-070-g12-fix-remeasurement.md`](benchmark/task-070-g12-fix-remeasurement.md)
- [`task-075-t03-forensic-trace.md`](benchmark/task-075-t03-forensic-trace.md)
- [`task-078-oracle-adjustment-sufficiency.md`](benchmark/task-078-oracle-adjustment-sufficiency.md)
- [`task-079-residual-confounding-forensics.md`](benchmark/task-079-residual-confounding-forensics.md)
- [`task-084-code-reviewer-verification.md`](benchmark/task-084-code-reviewer-verification.md)
- [`task-084-economic-impact-forensics.md`](benchmark/task-084-economic-impact-forensics.md)
- [`task-087-code-reviewer-verification.md`](benchmark/task-087-code-reviewer-verification.md)
- [`task-093-ecommerce-g12-regrade.md`](benchmark/task-093-ecommerce-g12-regrade.md)
- [`task-094-k1-selection-scoping.md`](benchmark/task-094-k1-selection-scoping.md)
- [`task-099-sample-size-detectability-preregistration.md`](benchmark/task-099-sample-size-detectability-preregistration.md)
- [`task-100-sample-size-detectability-results.md`](benchmark/task-100-sample-size-detectability-results.md)
- [`task-103-official-grading-results.md`](benchmark/task-103-official-grading-results.md)
- [`task-104-trap-fixture-results.md`](benchmark/task-104-trap-fixture-results.md)
- [`task-105-single-condition-confounding-threat-model.md`](benchmark/task-105-single-condition-confounding-threat-model.md)
- [`task-106-fn-autopsy.md`](benchmark/task-106-fn-autopsy.md)
- [`task-107-benchmark-v2-specification.md`](benchmark/task-107-benchmark-v2-specification.md)
- [`task-107-freeze-manifest.md`](benchmark/task-107-freeze-manifest.md)
- [`task-108-rescore-comparison.md`](benchmark/task-108-rescore-comparison.md)
- [`task-108-scorer-trap-classification-spec.md`](benchmark/task-108-scorer-trap-classification-spec.md)
- [`task-109-first-blind-engine-run-results.md`](benchmark/task-109-first-blind-engine-run-results.md)
- [`task-109-preregistration.md`](benchmark/task-109-preregistration.md)
- [`task-110-specific-recovery-autopsy.md`](benchmark/task-110-specific-recovery-autopsy.md)
- [`task-111-h111-falsification.md`](benchmark/task-111-h111-falsification.md)
- [`task-112-specificity-neutral-score-results.md`](benchmark/task-112-specificity-neutral-score-results.md)
- [`task-113-h113-post-intervention-autopsy.md`](benchmark/task-113-h113-post-intervention-autopsy.md)
- [`task-114-h114-nested-refinement-autopsy.md`](benchmark/task-114-h114-nested-refinement-autopsy.md)
- [`task-115-validation-preserving-refinement-results.md`](benchmark/task-115-validation-preserving-refinement-results.md)
- [`task-116-capacity-allocation-autopsy-results.md`](benchmark/task-116-capacity-allocation-autopsy-results.md)
- [`task-117-trajectory-results.md`](benchmark/task-117-trajectory-results.md)

### Product

- [`customer-review-workflow.md`](product/customer-review-workflow.md)
- [`finding-detail-screen.md`](product/finding-detail-screen.md)
- [`finding-feedback-contract.md`](product/finding-feedback-contract.md)
- [`finding-product-contract.md`](product/finding-product-contract.md)
- [`findings-list-screen.md`](product/findings-list-screen.md)
- [`policy-backtest-screen.md`](product/policy-backtest-screen.md)
- [`policy-candidate-domain-model.md`](product/policy-candidate-domain-model.md)

### Operations

- [`deployment.md`](operations/deployment.md)

### Security

- [`task-037-pre-customer-review-prep.md`](security/task-037-pre-customer-review-prep.md)
