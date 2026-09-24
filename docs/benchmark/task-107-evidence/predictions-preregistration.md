# TASK-107 Phase 1 - predictions committed BEFORE any measurement run

Author: STATISTICS. Written 2026-09-24. No script in this directory had been executed when this file was committed
(only the design inputs below were read: the engine atom grid and feature marginals of the committed v1 dataset,
never an outcome-conditional quantity, and never any v2 draw). No engine evaluation on v2 is performed in Phase 1.

Prior knowledge (disclosed): the authors know from TASK-106 that v0.6.2 has no candidate with exposure-Jaccard >= 0.5 for any
pattern, that P01 is oracle-detectable in 61/61 draws, P06 in 34/61 (projection) / 53/61 (exact), P03 25/61 / 57/61,
P04/P08/P09 0/61, and that T01/T02/T05 bare rules stop at G03. This knowledge is a risk to the neutrality of the v2 target
design and is disclosed in the specification (section on prior-knowledge risk).

## A. Jaccard sanity (`jaccard_sanity.py`, real v1 ground truth, committed dataset)

Selection rule for the proposed "specific" definition (fixed now): a definition is preferred iff, measured only on
fixtures constructed from ground-truth rules and on exhaustive engine-language enumeration (NOT on v0.6.2 candidates), it
(a) rejects every TASK-108 section-3 vacuous-threshold / bare-trap-exposure fixture, (b) accepts the exact rules and the
grid projections of the exact rules, (c) does not accept a rule solely because condition names/directions match while its
exposure is a several-fold superset. v0.6.2 candidates are scored afterwards, for illustration only.

Predictions (each falsifiable):
1. A1: condition-set Jaccard is 0.5 for both ADR-106 shapes (analytic; certain).
2. A2: on P02 (4 true conditions) the real exposure-Jaccard of "2 true conditions, nothing extra" and of "3 true + 2
   spurious" differ by more than 0.2 in the median, i.e. the ADR pair is NOT conflated by exposure-Jaccard even though
   condition-set Jaccard conflates it.
3. A3: exposure-Jaccard has its own conflation: among enumerated engine-language rules with exposure-J >= 0.5 there exist,
   for at least 2 of the 7 scoreable patterns, both a "dilute" rule (recall >= 0.9, precision < 0.75) and a "partial" rule
   (precision >= 0.9, recall < 0.75).
4. A4: at most 3 of the 7 scoreable patterns (P01, P03, P06 expected) have any engine-language rule (depth <= 3, eligible
   proxy) with exposure-J >= 0.5; P04, P08, P09 have none (P02 none).
5. A5: among enumerated rules with exposure-J >= 0.5, a non-zero number contain an effective condition matching no true
   condition (Cp < 1); a majority of J >= 0.5 rules have Cr < 1 for the patterns that have any.
6. A6: every TASK-108 section-3 vacuous / bare-trap-exposure fixture has exposure-J < 0.2 against every pattern (so an
   exposure-Jaccard floor alone closes the section-8 open item, provided the trap exemption is keyed to SPECIFIC rather
   than lenient recovery); a condition-level precision/recall rule alone (Cp>=2/3, Cr>=2/3) accepts at least one of them
   (`paid_search AND customer_type=new` vs P03).
7. A7: the v0.2-v0.5 historical precise P06 shape has exposure-J about 0.705 and all effective conditions matched; the
   P01 "two of three" shape (v0.6.2 CAND-005) has exposure-J about 0.26, Cp = 1, Cr = 2/3.

## B. Oracle detectability of the v2 candidate targets (`oracle_detectability.py`, prototype generator, calibration seeds)

Oracle = real, unmodified `run_validation` (contract 1.3.0) on the true rule; "pass" = evidence level >= predictive_association.
Multiplicity family fixed at 36,791 (sensitivity 26,213 and 60,000). Calibration seeds are separate from the acceptance seeds
(which Phase 2 will run once, on the frozen generator).

Pre-registered bands for P(pass) of the exact-condition oracle over calibration seeds (n=40):

| Target | dose | expected full-cohort n | predicted P(pass) |
|---|---|---|---|
| N01 corporate & Reykjavik & lead<23 | H | 100-160 | >= 0.85 |
| N02 premium & partner & discount>=0.08 | M | 280-420 | 0.6-1.0 (coarse discrete threshold, G12 risk) |
| N03 Cedar & family & duration>=10 | H | 150-230 | >= 0.85 |
| N04 Manager 6 & Rome & installments>=2 | M | 80-130 | 0.3-0.85 (small n, coarse threshold) |
| N05 corporate & wallet | M | 120-200 | 0.6-1.0 |
| N06 Lisbon & referral | M | 220-340 | >= 0.85 |
| N07 Manager 7 & direct & duration>=8 | H | 130-210 | >= 0.85 |
| N08 card & family & installments>=3 | L | 260-420 | 0.3-0.9 (low dose, coarse threshold) |
| O1 (4 conditions) Rome & family & party>=5 & premium | H | 85-145 | 0.6-1.0 (statistical); engine-language: not expressible (4 > 3) |
| O2 (calendar) Manager 8 & leisure & booking_month IN [1,2,12] | H | 120-190 | >= 0.8 as idealised atom; not expressible |

Further predictions: B1 targets with a coarse discrete numeric threshold (N02, N04, N08) show lower pass rates than
same-dose categorical-dominated targets; B2 the grid-projection oracle equals the exact-condition oracle within 10
percentage points for the grid-aligned targets N01-N08; B3 bare T03 and T04 rules reach predictive in >= 50% of seeds, while
bare T01, T02 and T05 reach predictive in < 20% (they stop at G03/G05, as TASK-106 D6), which makes them low-temptation
traps; B4 prototype fidelity: with no v2 targets the prototype reproduces the real generator rows exactly.

Dose definitions (effect config, EUR additional-cost shift / cancellation logit / support-rate): H = 410 / 1.05 / 0.75
(= P01's configured effect); M = 300 / 0.75 / 0.50; L = 240 / 0.50 / 0.30. Doses were fixed from P01's configured effect
before any draw; they were not tuned.

## C. What will not be done in Phase 1
No engine run on any v2 draw; no scoring of engine output under the proposed definitions except the already-committed v0.6.2
v1 candidates (illustration); no change to any repository generator/scorer/engine/gate/threshold.
