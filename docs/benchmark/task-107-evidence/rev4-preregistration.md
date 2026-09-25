# TASK-107 Phase 2b pre-declarations (Rev 4, Step 1) - committed BEFORE any calibration run

Binding: `ADR-106`, `ADR-107`, `ADR-108`, spec sections 2-4, 11-12. Engine frozen (`fefceeaac20e8ff7...`, contract 1.3.0). No engine or
discovery run on any v2 draw, ever, in this phase.

## 0. Disclosure of what was run and seen BEFORE this file was committed (plain statement, not backdated)

Step 0 (scorer, commit `b20d93a`) was committed first. After it, and BEFORE this pre-declaration commit, the following was run. Nothing
here touched a calibration seed (2001-2030) or any acceptance/final seed.

| What | Script | Seeds | What was seen |
|---|---|---|---|
| Atom-grid stability (real `_atoms`, covariates only) | `grid_explore.py`, `grid_stability.py` | 9001-9010 | which numeric thresholds are grid atoms in 10/10 draws |
| Contract-free Welch-t power proxy of the Phase 1 N-targets | `power_proxy_anchor.py` | 1001-1006 (Phase 1, already spent) | proxy t vs Phase 1 oracle rates (anchor) |
| Structural + proxy checks of DRAFT composites | `design_checks.py` | 9001-9010 | prevalence, proxy t, overlaps, K(T)=T, on-grid |
| Bounded dose-selection on the proxy (draft specs A, B, C) | `design_dose_select.py` | 9001-9010 | proxy t per design and rung; several rounds |
| Margin sd with/without targets | `margin_sd_check.py` | 9001 | sd 693 (none) vs 1272 (heavy draft composite) |
| **REAL ORACLE (run_validation, family 60,000) on the DRAFT-1 composite** (19 designs incl. manager-literal designs) | `v2_oracle.py` | **9001 (1 seed), then 9001-9010** | per-target pass counts and failed gates; the G12 detail strings |
| Reading of `validation/apply.py` G12 code | - | - | G12 leave-one-`manager`-out; robustness_group_column = manager |

Consequences, stated plainly:
1. Oracle-detectability results on the draft-1 composite WERE seen on seeds 9001-9010 before designs were finalised. Those ten seeds are
   **spent** for design purposes ("design seeds"). They are never used for calibration, acceptance or final evaluation.
2. That pilot showed every design with a `manager=` literal and no numeric condition fails G12 structurally (leave-one-manager-out drops
   the target's own rows: 8/9 = 89% sign agreement < 90%). All manager-literal designs are therefore EXCLUDED from Core candidates, on
   oracle-structure grounds (contract code + pilot), not engine grounds. This is a benchmark limitation to be reported (T01 is a manager trap).
3. No calibration seed (2001-2030 or later ranges) has been drawn, validated, or inspected.
4. The design/proxy scripts, spec drafts A/B/C and the pilot logs are committed as evidence; the draft `synthetic_benchmark_v2_targets.py`
   is NOT part of this commit (final designs are committed in a separate later commit, before calibration).

## 1. Seed ranges (defined now; disjoint; recorded)

| Role | Seeds | Note |
|---|---|---|
| Phase 1 calibration (spent) | 1001-1030 | never reused |
| Design seeds (spent, proxy + one oracle pilot seen) | 9001-9010 | see section 0 |
| Design hold-out pilot (one real-oracle run allowed, confirm-only, section 3) | 9101-9110 | |
| **Phase 2b calibration, round 1** | **2001-2030 (30 seeds)** | one run of the final composite; C5 re-run on the same seeds |
| Calibration round 2 (only if a NEW design set is needed, section 4) | 2101-2130 | |
| Acceptance A (Phase 2c) | 3001-3030 | not touched in 2b |
| Acceptance A' / A'' (fresh redesign sets) | 3101-3130 / 3201-3230 | not touched in 2b |
| Final evaluation E (F4) | 4001-4030 (reserve 4101-4130) | not touched |

## 2. Optional-stopping ban (ADR-108)

No acceptance or calibration run is extended with extra seeds after its result is seen; seed counts are fixed as above (30 each). A run
that fails is not "topped up". Redesign of any target requires a fresh, disjoint A' (and, for calibration, the round-2 range).

## 3. Dose-selection: a bounded design-stage procedure, otherwise forbidden

Allowed ONLY before the design-freeze commit, ONLY on design seeds 9001-9010, ONLY with the contract-free proxy of `design_dose_select.py`:
each design has a fixed rule and a fixed effect-structure ladder (`mixed`, `loss`, `cancel`; rungs in `synthetic_benchmark_v2_targets.LADDERS`);
rung = first rung with proxy t_mean >= 7.0 and t_min >= 5.8 (Core candidates, DECLARED_OVERLAP), or t_mean >= 5.0 (Challenge candidates);
whole composite re-evaluated after each change, at most 12 rounds; a design that fails at its top rung is dropped from the Core list (kept in
the log). Thresholds 7.0/5.8 come from the Phase 1 anchor (N02/N03/N06 passed 30/30 at proxy mean 6.0-7.7, min >= 5.1; N07 at 5.9/5.05 failed
7/30 on G05), set BEFORE the final run of the procedure. The design rules themselves were revised by hand at the design stage on the draft
specs A -> B -> C (documented by the committed spec files); no revision is allowed after the design-freeze commit.
One real-oracle confirm-only pilot on the hold-out seeds 9101-9110 is run BEFORE the design-freeze commit: a Core candidate that fails any of those
10 seeds is dropped from the Core list (not re-dosed), and the drop is recorded.
After the design-freeze commit: NO change of any rule or dose (forbidden). A design that fails calibration is classified by section 5 and recorded.

## 4. If fewer than 8 look acceptable after calibration

Do not lower tau; do not re-dose. Design additional NEW targets, freeze them in a new commit with new predictions, calibrate the new composite on
round-2 seeds 2101-2130, and only then run acceptance on fresh A (3001-3030 or A'). Reported in the final report, not silently iterated.

## 5. Classification rules (mechanical; inputs are outcomes only; no post-hoc reassignment)

Structural checks per target (all must hold on every seed of the run): L1 (<= 3 conditions), L2 (engine features), L3 (eq for categorical,
ge/lt on a grid atom for numeric), L4 (one condition per feature), L5 (build_projection Jaccard >= rho_rep = 0.80 on every seed), K(T)=T at nu = 0.05
(sequential vacuity drops nothing), C3 (no trap literal) unless the design is declared `declared_overlap` (then C4: exposure-J against the bare trap
literal <= 0.30 on every seed), scoreable (>= 50 affected, >= 40 development) on every seed.
Oracle result per seed: `pass` iff the true rule, graded by the real `run_validation` (contract 1.3.0) at family 60,000 on the composite draw, reaches
`predictive_association` or above; an unscoreable seed counts as a failure. k = passes out of S = 30.

* **CALIBRATION verdict (on 2001-2030; decides only which targets go to acceptance)**: `core_candidate` iff k = 30/30 and all structural checks hold
  and design class is core_candidate/challenge_candidate-not-declared; `overlap_candidate` iff declared_overlap and k = 30/30 and checks hold;
  `challenge_candidate` iff 15 <= k <= 29 (or k = 30 with a structural-check failure other than L1-L4); `underpowered` iff k < 15 or not scoreable on >= 20 seeds;
  `out_of_language` iff L1-L4 fail (never expected).
* **ACCEPTANCE class (Phase 2c, on fresh A; the only binding class)**:
  * **Core** iff not declared_overlap AND k = 30/30 AND one-sided 95% Clopper-Pearson lower bound >= 0.90 (30/30 gives 0.905) AND all structural checks hold on all 30 seeds.
  * **DECLARED_OVERLAP** iff the design contains a trap literal (structural, by declaration); `oracle_qualified` iff 30/30 and CP-LB >= 0.90 and C4 holds; non-qualified overlap targets are reported but excluded from that stratum's denominator. Never in Core or Challenge.
  * **Out-of-language** iff not overlap and L1-L4 fail, or L5 fails (min projection J < 0.80) while the oracle passes on >= 27/30 (own stratum, own denominator).
  * **Challenge** iff not Core, not overlap, not out-of-language, and 15 <= k <= 29 (own Challenge Recall; never in the Core denominator).
  * **Underpowered** otherwise (k < 15, or scoreable on < 20 of 30 seeds): reported, in no recall denominator.
  A design intended as Challenge that reaches Core-level results is Core; a design intended as Core that fails is Challenge or Underpowered: the class follows the outcomes, never the intention.

## 6. Structural design rules (checked on the design seeds; recorded in `design_checks.py`)

R1 no v1 pattern literal (D11); R2 no trap literal outside declared_overlap (C3); R3 two targets share at most one categorical literal; R4 no target's
rows nested in another's; R5 pairwise overlap coefficient |A_i & A_j| / min(|A_i|,|A_j|) <= 0.25 on every design seed; R6 thresholds only on grid atoms present in
10/10 design draws (discount_rate ge 0.05/0.08/0.12, party_size ge 3/4, trip_duration_days ge 6/8; continuous price/cost and unstable lead-time thresholds are not used);
R7 no `manager=` literal in any Core candidate (section 0, item 2); R8 no seasonal literal (Zanzibar excluded from Core candidates); R9 T01-T05 unchanged.

## 7. Prior-knowledge disclosure (v0.6.2)

The authors know v0.6.2's behaviour on v1 (broad candidates, 0 specific matches on v1). Target selection here used only oracle-structure facts (the contract's
G05 family arithmetic, the G12 leave-one-manager-out design, Phase 1 oracle rates on spent seeds) and a contract-free power proxy; no engine output on any v2 draw
exists or was consulted; no design was chosen or dropped by what v0.6.2 finds or misses. Residual risk: choosing rules that are categorical, low-order and
engine-expressible is itself informed by knowing the engine language; this is an inherited, un-removable bias, stated here.

## 8. Predictions

Per-design predictions are committed together with the frozen designs (next commit), still before any calibration run.

## 9. Amendment A1 (design stage, before the design-freeze commit and before any calibration run)

Rule R5 (pairwise overlap coefficient <= 0.25) was violated by Challenge designs in the last design iteration (max 0.32, H03|D01; all Core-Core pairs <= 0.25).
Rather than iterate further, R5 is AMENDED to <= 0.35 for pairs that involve a Challenge candidate; Core-Core and Core-overlap pairs keep <= 0.25.
This is a relaxation made after seeing the check output; it is disclosed here and in the spec. Design iterations D -> E used the proxy on seeds 9001-9010 only.

## 10. Amendment A2 (design stage, before freeze): hold-out pilot #1 result and one further design round

Hold-out pilot #1 (9101-9110, design-spec-E composite, 17 designs) was RUN AND SEEN: Core candidates C03 (8/10, G12) and C05 (9/10, G12) failed, plus overlap D02 (7/10) and challenge H03 (8/10); the other 10 Core candidates passed 10/10. By section 3 C03 and C05 are dropped from the Core list. Because exactly 10 Core candidates would remain (too little margin for >= 8 acceptance survivors), three NEW Core candidates C13-C15 (design-spec-F) are added, doses chosen by the same procedure on 9001-9010, and a SECOND confirm-only pilot is run on fresh seeds 9111-9120. Section 3 applies again: a Core candidate failing any of those 10 seeds is dropped from the Core list (kept in the composite, recorded as dropped_pre_calibration). Seeds 9101-9110 and 9111-9120 are spent afterwards.

## 11. Amendment A3 (design stage, before freeze)

R5 is AMENDED again, to a single bound of <= 0.45 for every pair (observed max 0.452 on C15|H03, next 0.388); R1-R4, R6-R9 unchanged. Reason: with the many common levels (returning, standard, card, corporate) a 0.25 bound cannot be met by rules that also share <= 1 literal without further iteration; overlap is additive-effect coupling whose actual consequence is measured on the composite in calibration. This is a relaxation made after seeing check output and is disclosed as such (spec Rev 4).
