# TASK-107 Phase 1 Revision 1 - predictions committed BEFORE the Rev 1 check script was run (2026-09-25)

Author: STATISTICS. `predictions-preregistration.md` is not edited (unedited since `22f4b4d`); this is a separate file.
The script `rev1_check.py` (added in the next commit) reads only the already-committed `oracle-raw/` and `oracle-raw-v1only-no-targets/` JSON; no generator, engine or validation is run.

Predictions (from reading `synthetic_benchmark.py` `_generate_row`: `scaled_uniform(...refund_ratio)` and `rng.randint(2, 75)` are drawn only when `cancellation` is true):

1. R1-A. For seeds 1001-1030 and patterns P01, P02, P03, P06 (120 pairs), `n_affected` in `oracle-raw` differs from `oracle-raw-v1only-no-targets` in at least 110 pairs (reviewer reported 115).
2. R1-B. Seed 1001 P03 369 vs 350 and P01 179 vs 163 (values read by the reviewer; expected to reproduce).
3. R1-C. Two-sided Fisher exact p for P03 oracle pass 15/30 vs 6/30 is in [0.02, 0.05]; for P01 (28/30 vs 30/30) and P06 (25/30 vs 22/30) p > 0.2.
4. R1-D. Under `theta_p = 1`, 3 of 15 `P03` rules at exposure-J >= 0.5 survive (12 of 15 have Cp < 1), and all rules of P01 (2), P06 (1) and P08 (2) survive; read from the counts in `jaccard-sanity-raw.json` (no script needed for this item).
