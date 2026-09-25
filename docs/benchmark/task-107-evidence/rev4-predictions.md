# TASK-107 Phase 2b predictions (committed with the design freeze, BEFORE any calibration run on seeds 2001-2030)

## A4 design-stage record (final, disclosed)

Design-stage sequence: spec A -> B -> C -> D -> E -> F -> G (files `design-spec-*.json`, `rev4-design-stage/sel*.json`). Hold-out pilots (real oracle, family 60,000,
primary): #1 seeds 9101-9110 on spec E; #2 seeds 9111-9120 on spec F; #3 seeds 9121-9130 on spec G (the final composite). All pilot seeds are spent.
Rule swap between F and G: C15 changed from `returning AND partner AND duration>=6` to `returning AND direct AND duration>=6` because the former shared two conditions with v1 `P07`
(D11 caution); doses re-derived by the section 3 procedure. Pilot #3 (final composite): C03 1/10 (G12), C05 9/10, C06 9/10 -> by section 3 these three are DROPPED from the Core list and
declared `challenge_candidate` (kept in the composite; recorded as dropped_pre_calibration). D02 6/10 (overlap; kept, expected not oracle-qualified). Also C03 and C05 had failed pilots #1/#2.
**Frozen composite: 20 targets = 12 Core candidates (C01, C02, C04, C07, C08, C09, C10, C11, C12, C13, C14, C15), 6 Challenge candidates (C03, C05, C06, H01, H02, H03),
2 DECLARED_OVERLAP (D01 with T03 literal, D02 with T04 literal).** Amendments A1-A3 of `rev4-preregistration.md` (R5 relaxed to <= 0.45) apply. No manager literal in any design (G12).
Design-seed structure check of the final composite: `rev4-design-stage/design-checks-final.txt` (no static errors, nothing nested, all K(T)=T and on-grid, all scoreable).

## Predictions for the calibration run (2001-2030, family 60,000 primary, true-rule oracle, real contract)

P1. Structural: K(T)=T, on-grid, L5 projection Jaccard = 1.0 and scoreable on all 30 seeds for all 20 targets. D01 bare-trap Jaccard max < 0.30; D02 max close to 0.28 (probability 0.75 that it stays <= 0.30 on all 30 seeds).
P2. Core candidates: per-seed oracle pass probability >= 0.97 for each of the 12. Expected number with 30/30 on calibration: 9-11 (median 10); P(>= 8) about 0.85; P(all 12) about 0.10.
P3. Dropped Core (C03, C05, C06): observed rates 60-95%; P(30/30) < 0.15 each. H01, H02, H03: observed rates 80-100%; P(30/30) about 0.3 each.
P4. D01: observed rate >= 0.95, P(30/30) about 0.5. D02: observed rate 0.40-0.75, P(30/30) < 0.03 (not oracle-qualified).
P5. Dominant failing gate: G12 (sign-agreement floor of 9 or 11 perturbations) first, G05 second. Sensitivity families: 36,791 and 26,213 counts >= the 60,000 counts for every target.
P6. Composite properties (design seeds): rows carrying at least one target effect about 70%; margin sd inflated relative to no targets; disclosed as a benchmark property, not a defect.
P7. C5 on the composite (seeds 2001-2030, reference only): `T03` composite reaches predictive_association in >= 25/30; `T01`, `T02`, `T04`, `T05` in <= 3/30 each; no composite reaches shadow_policy (G16).
P8. Composite coverage verdict (falsifiable): >= 8 targets of the 12 have calibration verdict `core_candidate` (30/30). If fewer, section 4 of the pre-registration applies (design new targets, new round-2 seeds, do not lower tau).
