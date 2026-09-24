# Jaccard sanity - prediction outcomes (written after the run; predictions file untouched)

Raw: `jaccard-sanity-raw.json` (run after commit 22f4b4d). Enumeration: 122,674 engine-language rules (depth <= 3), 108,236 pass the eligibility proxy.
Note: the enumeration's condition-set-J counts are restricted to rules with recall >= 0.5 or exposure-J >= 0.3 (prefilter, disclosed in the script).

| Pred | Outcome |
|---|---|
| A1 condition-set J = 0.5 for both ADR shapes | CONFIRMED (analytic) |
| A2 exposure-J separates the ADR pair on P02 by > 0.2 median | NOT CONFIRMED as stated. "2 true, nothing extra" (6 rules) has exposure-J 0.084-0.396, median about 0.22; "3 true + 2 spurious" (10,900 rules) has median 0.103, 3.5% >= 0.5. Difference about 0.12. Exposure-J does rank the two shapes differently, but the gap is under the predicted 0.2; both are mostly < 0.5. |
| A3 both a dilute and a partial rule among J >= 0.5 for >= 2 patterns | FALSIFIED. Dilute rules exist (P01, P02, P03, P06, P08) but there is NO partial (precision >= 0.9, recall < 0.75) rule with J >= 0.5 anywhere. Mechanically, J >= 0.5 with a subset exposure needs recall >= 0.5; the sub-0.75-recall region is empty in this pool. |
| A4 at most 3 patterns have any J >= 0.5 rule (P01, P03, P06), none for P08 | FALSIFIED in part. J >= 0.5 rules exist for P01 (2), P03 (15), P06 (1) AND P08 (2: the exact grid projection 0.952 and `party_size<3` 0.541). None for P02, P04, P09. So 4 of 7. |
| A5 non-zero J >= 0.5 rules with a spurious effective condition; majority have Cr < 1 | CONFIRMED for the first part (P03: 12 of 15 with Cp < 1; P08 1 of 2 ...). The second part holds for P03 (14 of 15) and not for P01/P06 (all 3 conditions matched). |
| A6 every TASK-108 sec.3 vacuous/bare fixture has exposure-J < 0.2; condition-level rule accepts one | PARTLY FALSIFIED. Nine of ten fixtures have exposure-J <= 0.195. `paid_search AND installments>=3 AND discount_rate>=0.03` has exposure-J 0.507 against P03 (431 exposed vs 333 affected, recall 0.87 ... one spurious effective condition, Cp 0.67). It is a J >= 0.5 rule that TASK-108 keeps as a trap (discount_rate is not in P03's rule; discount_rate IS T03's confounder). Condition-level (Cp, Cr >= 2/3) accepts `bank_transfer AND lead<60` and `paid_search AND customer_type=new` (exposure 1825 and 1706, J 0.07 and 0.195), as predicted. |
| A7 historical precise P06 J about 0.705 (all matched); P01 two-of-three J about 0.26, Cp = 1, Cr = 2/3 | CONFIRMED. Also: the historical P01 shape (J 0.504) is uniquely `lead<23 AND discount>=0.08 AND BlueWing` (recall 1.0, precision 0.5). |

Additional observations (not pre-registered, reported as observed):
* Exposure-J >= 0.5 rules are rare and cluster on grid projections. Counts of enumerated rules at exposure-J >= 0.3/0.5/0.7: P01 5/2/1, P02 11/0/0, P03 45/15/1, P04 0/0/0, P06 4/1/1, P08 10/2/1, P09 3/0/0.
* Condition-set J is nearly uninformative about exposure: for P02 at condition-set J = 0.5 the exposure-J ranges 0 to 1.0 with median 0.10-0.2; for P01/P03 at condition-set J = 0.667 the exposure-J median is about 0.25. Two of three conditions "correct and nothing extra" gives exposure-J 0.17-0.28 for P01/P03/P06 (each dropped condition multiplies exposure 4-6x).
* All 15 v0.6.2 run1 candidates have best exposure-J <= 0.086 for 14 of 15 (CAND-005 = 0.261) while 1 to 7 patterns are lenient matches per candidate (CAND-004: 7 patterns).
