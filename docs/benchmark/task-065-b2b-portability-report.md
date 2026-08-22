# TASK-065 b2b_sales/comparable portability evaluation

**Run:** `task-065-b2b-comparable-20260822-001`  
**Date:** 2026-08-22  
**Owner:** Independent Statistics evaluator  
**Procedural status:** DONE  
**Analytical portability verdict:** FAILED

**Deeper analysis:** `docs/benchmark/task-065-b2b-portability-postmortem.md` reads the same frozen
artifacts in far more depth — per-candidate gate detail, a domain-contract comparison against
travel, an 8-category root-cause analysis, a methodology-defect-vs-domain-adaptation determination,
and a preregistered next experiment. This report is not edited to change any figure below; it
remains the original closing summary.

## Custody and sequencing

The evaluator declared no participation in discovery or candidate selection, no prior exposure to
the b2b hidden ground truth, and no inherited context from the Statistics actor recused by ADR-048.
The archived candidate SHA-256 was rederived as
`ec3b1c17c9826724dfaa6adec1a1db431768bad772b228d33cf906be6ab49bcc`, matching the signed receipt
and Code Reviewer's `CUSTODY_VERIFIED` record in HANDOFF-067.

TASK-019 ran first against frozen candidates and the public analytical dataset. Hidden truth was
not opened. The resulting report was made read-only, hashed, and rechecked as `status=FROZEN` with
`hidden_ground_truth_opened=false`. Only then did TASK-028 open exactly the preregistered
`b2b_sales/comparable` hidden truth. No discovery or validation code, threshold, matching rule, or
methodology changed during the cycle.

## PHASE A — validation

- Artifact: `artifacts/validation/task-019-task-065-b2b-comparable-20260822-001.json`
- SHA-256: `873db1f40a4c35ef693f8195dd2cc046164847c803f60c7de85112a27bf69f3c`
- Contract: validation v1.2.0; provisional outcome contract v0.1.0
- Verdicts: 0 PASS, 15 DOWNGRADE, 0 REJECT
- Evidence/readiness: 15 `descriptive_observation`; 15 `experiment_only`
- Uncertainty/multiplicity: G03, G04, and G05 passed for all 15 candidates using the fixed
  cluster-bootstrap and BH methodology.
- Confounding: G06 failed all 15. Raw harm estimates ranged from USD 14,590 to USD 22,371 per
  record, while adjusted estimates ranged from USD -376 to USD 2,223 and did not meet the fixed
  confounding gate.
- Stability: G10 and G12 passed all 15; holdout magnitude retention ranged from 95% to 99%, with
  the same raw sign in development, validation, and future holdout.
- Heterogeneity: G09 was `NOT_EVALUATED` for all candidates because the manifest declares no
  reviewed heterogeneity role. This conservatively caps evidence rather than manufacturing a pass.
- Materiality/impact: G15 passed all 15 on raw combined-window exposure; estimated historical
  exposure ranged from USD 29.5m to USD 79.9m. These are descriptive exposures, not savings or
  causal effects, and the confounder-adjusted evidence did not support policy promotion.

## PHASE B — hidden-truth evaluation

- Artifact: `artifacts/evaluation/task-028-task-065-b2b-comparable-20260822-001.json`
- SHA-256: `02ad8ca8996cd411cc3d86aa8ce6db41243ac55f456c2b07f6e5cbb0600ffca1`
- Hidden-ground-truth SHA-256 recorded by the evaluator:
  `37b038f9befed59b8b69f86cb98c13c4279123bc3060ffe925dc8787c179c9b6`
- Fixed match rule: affected-population recall at least 0.5; Top K = 10.
- Top-10 precision: 90% (9/10 candidate-level matches).
- Unique scoreable candidate recall: 1/6 (16.7%; B03 only).
- Validation-qualified recall: 0/6 (0%).
- Economic-weighted recall: 0.0%.
- Direction accuracy: not estimable (0 eligible validated and matched candidates).
- Median economic impact error: not estimable (0 eligible validated and matched candidates).
- Leakage violations: 0.
- Traps: BT02, BT03, and BT04 appeared in candidates; all five traps remained below promoted
  readiness. Trap promotion count: 0; trap rejection/downgrade: 5/5.

## Verdict

No hard disqualifier fired: there was no leakage, no promoted trap, and no eligible materially
wrong-direction finding. Nevertheless, the preregistered decision gate grades the run **FAILED**
because economic-weighted recall is below 5%. High candidate-level precision does not establish
portability when every candidate is downgraded after adjustment and no true pattern contributes to
validated recall. The procedure is complete, but the current mechanism did not demonstrate
portability to this first non-travel domain/variant.
