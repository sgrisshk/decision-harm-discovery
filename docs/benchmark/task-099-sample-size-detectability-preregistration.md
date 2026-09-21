# TASK-099 — Sample-size / statistical-detectability pre-registration (real public data, Olist)

**Owner:** STATISTICS
**Recorded:** 2026-09-21
**Status:** PRE-REGISTERED. **This document produces no data, runs no discovery, runs no
validation.** It specifies a design only. A dated freeze-point commit (this file's first commit to
this worktree branch) is the actual pre-registration event; everything above the line marked
"§12 Post-freeze mechanical amendments" was written and committed before a single row of the target
dataset was loaded. Running the experiment this document specifies is a separate, later task
(`TASK-099`'s own text: "opened only once this document is independently confirmed to actually
pre-register the design"), not performed here.

This document answers all seven items of `TASK-099`'s `TASKS.md` entry, in the numbering that
entry uses, plus the process-discipline items the assigning message added on top of it (a
git-freeze point before any data is opened, an honest blindness/process log, and an append-only
correction discipline for anything found only after data opens). It follows
`docs/benchmark/task-068-ecommerce-preregistration.md`'s house style: every parameter fixed now,
nothing left to define after results exist.

**Naming note, to avoid a collision.** `TASK-061` already defined a synthetic domain literally
named `ecommerce` (`docs/benchmark/task-068-ecommerce-preregistration.md`, spent per `ADR-054`).
The real, public dataset this document specifies is a *different* thing — Kaggle's "Brazilian
E-Commerce Public Dataset by Olist" — and is referred to throughout as **`olist`**, never
`ecommerce`, specifically so no later reader conflates the two.

---

## 0. What this experiment tests (restated from `TASK-099`'s origin, not reworded)

The founder's own framing, as `TASKS.md` records it verbatim: *"Holding the validation/safety
standards fixed, does increased effective sample size make additional independently defined target
patterns statistically detectable and recoverable?"* — deliberately separating three things a same-day
ad-hoc exploration conflated: **statistical detectability** (a power/multiplicity property of the
data and `n` alone), **search/discovery ability** (whether `discover_candidates()` finds and ranks a
detectable pattern), and **precision/safety after discovery** (whether what is found stays
trustworthy). This document pre-registers a design that keeps those three questions separate at two
scales of the same real data.

---

## 1. Process log — what was looked at before this document's freeze commit, and what was not

Stated plainly, as the actual provenance record `TASK-099`'s process discipline requires, not as an
assertion to be taken on faith.

**Looked at before drafting §5 (the hypotheses) and before the freeze commit:**
- The orchestrator's own message to this session, reproducing exactly nine CSV filenames, their row
  counts, and their column headers for the Olist dataset (reproduced verbatim in §2.1 below) — no
  more than that.
- Three public, generic facts about this dataset's well-documented design, explicitly pre-cleared by
  that message as safe: it is a real Brazilian marketplace's order history; `order_id` is the
  natural transaction/decision grain; the real-world date range is roughly 2016–2018.
- This project's own source code: `packages/analytics/src/policy_analytics/discovery/engine.py`
  (`DiscoveryConfig`, `discover_candidates`, `Condition`), `packages/analytics/src/policy_analytics/
  profiling/schema_profiler.py` and `.../profiling/feature_timing.py` (`TASK-007`/`TASK-008`'s real,
  disclosed, deterministic classification rules — read in full), `packages/analytics/src/
  policy_analytics/validation/apply.py` (`minimum_detectable_effect`, `run_validation` signature),
  `packages/analytics/src/policy_analytics/validation/grading.py` (`benjamini_hochberg_adjusted`),
  `packages/analytics/src/policy_analytics/validation/contract.py` (`ValidationThresholds`,
  `CONTRACT_VERSION = "1.3.0"`), `packages/analytics/src/policy_analytics/outcomes/contract.py`
  (`OutcomeDefinition`'s required fields), `apps/api/app/datasets/profiling.py` and `.../timing.py`
  (the real ingestion persistence wiring), `scripts/evaluate_benchmark.py` (`MATCH_RECALL_THRESHOLD`,
  `_affected_ids`, `_scoreable_pattern_ids`, `TOP_K`). **None of this is Olist data. It is this
  project's own already-public, already-committed code**, reading it is not a data-blindness
  violation, and doing so was necessary to specify a design that actually invokes the real pipeline
  rather than a hand-built substitute (`TASK-099` item 2's explicit requirement).
- `TASKS.md`'s `TASK-099` entry in full, `DECISIONS.md`'s `ADR-092` in full (including its
  2026-09-21 addendum), `docs/benchmark/task-069-validation-power-autopsy.md`,
  `docs/benchmark/task-069-oracle-decomposition.md` (cited, not fully re-read),
  `docs/benchmark/task-068-ecommerce-preregistration.md` (house style and custody-protocol
  precedent), `TASKS.md`'s "Ad-hoc note (2026-09-21...)" entry (the two leakage defects this task
  exists to avoid repeating), and `TASKS.md`'s `TASK-098` entry / `ADR-093` (why this task was
  opened at all).

**Explicitly not looked at, before the freeze commit, and not to be looked at before it:** any row
of any Olist CSV; any Olist summary statistic, distribution, correlation, or outcome value; any
external source (web search, prior training-data recollection treated as authoritative) asserting
specific Olist category values, effect sizes, or known findings from this dataset. Where a
hypothesis in §5 needed a concrete threshold, it is defined **relative to the data itself**
(a percentile, a frequency rank) rather than as a guessed absolute number, precisely so no outside
recollection of this dataset's actual values could leak into a threshold choice. This is stated here
so it is checkable: nowhere in §5 does a hypothesis depend on knowing what value a column actually
takes.

**Confirmed independently, not just asserted:** this session ran no Python, no shell command that
reads dataset bytes, and no query of any kind against the Olist files before the commit recorded in
§13. The commit hash itself, and a `git show --stat` of that commit touching only this file, is the
checkable record.

---

## 2. Item 1 — Dataset and the matched-scale comparison design

### 2.1 The schema, reproduced verbatim (the only Olist information used to write §5)

```
olist_customers_dataset.csv (99,441 rows): customer_id, customer_unique_id, customer_zip_code_prefix, customer_city, customer_state
olist_geolocation_dataset.csv (1,000,163 rows): geolocation_zip_code_prefix, geolocation_lat, geolocation_lng, geolocation_city, geolocation_state
olist_order_items_dataset.csv (112,650 rows): order_id, order_item_id, product_id, seller_id, shipping_limit_date, price, freight_value
olist_order_payments_dataset.csv (103,886 rows): order_id, payment_sequential, payment_type, payment_installments, payment_value
olist_order_reviews_dataset.csv (104,719 rows): review_id, order_id, review_score, review_comment_title, review_comment_message, review_creation_date, review_answer_timestamp
olist_orders_dataset.csv (99,441 rows): order_id, customer_id, order_status, order_purchase_timestamp, order_approved_at, order_delivered_carrier_date, order_delivered_customer_date, order_estimated_delivery_date
olist_products_dataset.csv (32,951 rows): product_id, product_category_name, product_name_lenght, product_description_lenght, product_photos_qty, product_weight_g, product_length_cm, product_height_cm, product_width_cm
olist_sellers_dataset.csv (3,095 rows): seller_id, seller_zip_code_prefix, seller_city, seller_state
product_category_name_translation.csv (70 rows): product_category_name, product_category_name_english
```

### 2.2 Decision grain and join specification (fixed now; mechanical row counts filled in §12)

The decision/transaction grain is `order_id` (given as a public, generic fact about this dataset's
design, not derived from opening it). The order-grain analytical table `F` is built by:

1. Start from `olist_orders_dataset` (one row per `order_id`).
2. **Item aggregation.** Group `olist_order_items_dataset` by `order_id`: `n_items` (row count),
   `total_price = sum(price)`, `total_freight_value = sum(freight_value)`, `first_product_id` and
   `first_seller_id` (the row with the lowest `order_item_id` within the order, a deterministic
   tie-break, not an outcome-dependent one). Inner-join onto `F` by `order_id` (an order with zero
   items is excluded — it cannot have been decided against any of this experiment's candidate
   features).
3. **Payment aggregation.** Group `olist_order_payments_dataset` by `order_id`: `total_payment_value
   = sum(payment_value)`, `max_installments = max(payment_installments)`, `modal_payment_type` (the
   payment_type with the largest row count within the order; ties broken lexicographically
   ascending on the string). Inner-join onto `F`.
4. **Review aggregation.** Group `olist_order_reviews_dataset` by `order_id`, keeping the row with
   the latest `review_creation_date` (a deterministic tie-break on `review_id` ascending if tied).
   **Left**-join onto `F` (an order may have zero reviews; `review_score` is null for those rows,
   handled by §5's outcome-eligibility cohort, not by dropping rows here).
5. **Customer join.** Inner-join `olist_customers_dataset` onto `F` via `orders.customer_id ==
   customers.customer_id`, bringing in `customer_state`, `customer_zip_code_prefix`,
   `customer_city`.
6. **Product/category join.** Left-join `olist_products_dataset` onto `F` via `first_product_id ==
   product_id`, bringing in `product_category_name`, `product_weight_g`, `product_photos_qty`, and
   the three dimension columns. Left-join `product_category_name_translation` onto that by
   `product_category_name` (informational only; not used by any pre-registered hypothesis, since
   `product_category_name` itself is already a decision-time-plausible categorical column and the
   English translation adds no new information a rule could condition on).
7. **Seller join.** Left-join `olist_sellers_dataset` onto `F` via `first_seller_id == seller_id`,
   bringing in `seller_state`, `seller_zip_code_prefix`, `seller_city`.
8. `olist_geolocation_dataset` is **not** joined. It is a zip-prefix-to-lat/lng lookup with no
   `order_id`, unrelated to any pre-registered hypothesis below, and pulling it in would multiply
   rows non-deterministically unless pre-aggregated by a rule not yet specified; leaving it out is
   the more conservative, more easily audited choice.

This join is specified completely enough to be executed identically by any later session; its
**mechanical output** (the resulting `N_F`, i.e. `len(F)`, and confirmation that every column named
in §5 actually survives the join under the name assumed) is exactly the kind of "confirming which
columns actually exist post-join" work `TASK-099`'s process discipline defers to §12, after this
freeze commit — not because the join *method* is undetermined (it is fully fixed above), only
because its *numeric result* requires opening the files.

### 2.3 Decision timestamp and temporal split

`order_purchase_timestamp` (the moment the order — the decision — is placed) is the decision
timestamp for every row of `F`. `F` is sorted ascending by this column (a deterministic order, no
randomness) and partitioned into `development` / `validation` / `future_holdout` using this
project's own existing, unmodified split-building tooling —
`scripts/build_domain_temporal_splits.py` plus `domain_benchmarks.analytical_bridge.
temporal_split_config` — the exact tool `TASK-062`/`TASK-065` already used to build
`b2b-sales-temporal-split-v1.0.0` and `ecommerce-temporal-split-v1.0.0` (`docs/benchmark/
task-068-ecommerce-preregistration.md` R2). **Whatever proportions that tool's existing, unmodified
default configuration produces for Olist's real date range is what is used here** — no new split
ratio is invented or tuned for this experiment. Call the resulting full-scale development partition
`D_F`.

### 2.4 Full-scale condition

`F`, split as in §2.3. `discover_candidates()` and every oracle computation in §7 read only `D_F`
(its own `split_label == "development"` filter, unmodified); `validation`/`future_holdout` partitions
are read only by the real validation pipeline's own existing gates (G10 holdout retention, etc.),
exactly as they are for every other domain — nothing about how a gate reads a split is changed here.

### 2.5 Matched-scale condition — the exact downsample method, fixed before any run

**The manipulation is applied to `D_F` only, not to `F` as a whole.** A fixed-seed, uniform,
without-replacement random sample of exactly **4,999 rows** (travel's own real development-split
row count — cited exactly, not "~5,000": `docs/benchmark/task-069-validation-power-autopsy.md` §3,
`ADR-092` Q1, `docs/benchmark/task-069-oracle-decomposition.md`, all independently give the same
figure) is drawn from `D_F`, using seed `1729` — this project's own standing seed constant, reused
verbatim from `DiscoveryConfig.seed`'s default and every blind run's `seed=1729`, not a new number
invented for this experiment (the same "reuse a constant already fixed under review" reasoning
`task-068-ecommerce-preregistration.md` §4a.1 used for `0.34`). Concretely:
`polars.DataFrame.sample(n=4_999, seed=1729, with_replacement=False, shuffle=True)`, or the
`numpy.random.default_rng(1729)`-driven equivalent if the row count of `D_F` requires a manual
index draw — either is acceptable provided the seed and sample size match exactly; the executing
session must record which was used. Call this table `D_M` (matched-scale development partition).

**`validation` and `future_holdout` are *not* downsampled in the matched-scale condition — they stay
identical, full-scale, and byte-for-byte shared with the full-scale condition.**

**Alternatives considered and rejected, before any run:**
- *Downsample all three splits proportionally to reach a ~4,999-row development split.* Rejected:
  this would also shrink `validation`/`future_holdout`, confounding "does more development-side data
  change detectability" with "does a noisier, smaller holdout change gate behavior" — two different
  effects on one knob, contrary to the founder's explicit separation of statistical detectability
  from downstream validation/discovery behavior. Holding `validation`/`future_holdout` fixed and
  identical across both conditions isolates the manipulation to exactly the quantity `TASK-099`'s
  own question is about: development-side effective sample size. It also means any later difference
  in G10 holdout retention between scales is attributable only to what a candidate found on a
  smaller development set predicts on the *same* held-out data, not to the holdout itself changing.
- *A principled temporal truncation (e.g., "first `k` months") instead of a random sample.* Rejected
  as the primary method: a temporal truncation confounds sample size with seasonality/composition
  drift (exactly the class of confound `G09`/`G11` exist to detect, and which this design should not
  introduce as a side effect of downsampling). A fixed-seed uniform sample avoids that confound by
  construction; it is the same class of choice `task-068-ecommerce-preregistration.md` §1a.3 states
  "every parameter... fixed... on domain-neutral grounds only."

### 2.6 What "matched" and "full" mean going forward

Every subsequent section (`§7`) runs identically on `(D_F, \text{validation}, \text{future\_holdout})`
and on `(D_M, \text{validation}, \text{future\_holdout})` — the same code, the same
`DiscoveryConfig()`, the same `ValidationThresholds`, the same pre-registered rules from §5, differing
only in which development table is passed in.

---

## 3. Item 2 — Real feature classification, and which of the two named paths is used

`TASK-099` item 2 offers two options and requires this document to pick one: route the joined
structure through `TASK-008`'s classifier directly, or through a CSV export via the real ingestion
API. **This document specifies the direct route — calling `schema_profiler.profile_columns()` then
`feature_timing.classify_columns()` on an in-memory frame built from a CSV export of `F`** — and
states why, rather than the full `POST /api/v1/datasets` HTTP path.

**Reasoning, checked against the actual code, not assumed.** `apps/api/app/datasets/profiling.py`'s
`profile_dataset` does exactly two things: `frame = pl.read_csv(csv_path, infer_schema_length=0)`
then `profiles = profile_columns(frame)` — persistence (`DatasetColumnProfileModel` rows) is the
only thing added beyond the pure function call. `apps/api/app/datasets/timing.py`'s
`classify_dataset_timing` is the same shape: `classifications = classify_columns(profiles)`, then
persistence. **Neither file contains any classification logic of its own** — `TASK-008`'s actual,
deterministic, disclosed rules live entirely in `policy_analytics.profiling.schema_profiler.
profile_columns` and `policy_analytics.profiling.feature_timing.classify_columns`, which this design
calls directly. The HTTP/DB layer is I/O plumbing around those two pure functions, not a second
classification stage; calling them directly produces byte-identical classification output to the
full HTTP path, and this is verified by reading the two files above rather than assumed. This is the
same distinction `TASK-099`'s own origin note draws: the defect in the same-day ad-hoc exploration
was **bypassing `classify_columns()` entirely** in favor of hand-built `feature_roles`, not
bypassing the ephemeral-Postgres HTTP wrapper around it. Calling the real functions directly, while
skipping only the unrelated persistence/HTTP layer, satisfies item 2's actual purpose without
requiring a running API server and database for a dataset this large, purely to reproduce a result
the pure functions alone already determine.

**Fidelity requirement, fixed now.** The CSV export of `F` fed to `profile_columns` must be read
with the identical parameter the real path uses — `pl.read_csv(path, infer_schema_length=0)` (forces
all columns to string, matching how the real upload path is read) — so the profiler sees the same
raw representation it would see from a real upload, not a polars-inferred-dtype frame that could
change `ColumnProfile.inferred_type`/`semantic_type_guess` results.

**What is *not* authorized by this section:** hand-constructing `feature_roles` or a `ValidationInput`
in place of this call, for any reason, including convenience. Every feature that enters `§7`'s
`discover_candidates()` call must be a column `classify_columns()` itself labeled `DECISION_TIME`,
read from its actual output at execution time — never asserted here in advance. §5 explains which
outcome is which classification is *expected*, from the classifier's own disclosed rules read in
§1, but expectation is not authorization to skip the real call.

---

## 4. Item 3 — Proxy/leakage exclusion protocol

The exact failure mode found twice in `TASKS.md`'s "Ad-hoc note (2026-09-21...)" entry: a candidate
feature arithmetically or definitionally entangled with the outcome, because both were computed by
summing/deriving from the *same underlying rows*. This section fixes the check, in two parts, before
any feature is treated as a valid decision-time input.

### 4.1 Construction-provenance check (done now, blind, in §5's own hypothesis design)

For every candidate feature named in §5, trace its defining source table against the outcome's
defining source table (§5's two outcomes below). No candidate feature used in §5 is computed from
`olist_order_reviews_dataset` (the source of `OUTCOME_LOW_REVIEW`) or from the two delivery-date
columns of `olist_orders_dataset` (the source of `OUTCOME_LATE`) — every candidate feature derives
from `olist_order_items_dataset`, `olist_order_payments_dataset`, `olist_products_dataset`,
`olist_sellers_dataset`, or `olist_customers_dataset`, which are wholly disjoint source tables from
either outcome's own source. This is the direct analogue of the check that *would* have caught both
same-day defects (the leaking feature and the outcome were both row-level derivations of the same
invoice's line items) had it been applied before those two ad-hoc attempts. It is argued explicitly
per feature in §5, not asserted in bulk.

### 4.2 Empirical determinism audit (deferred to §12, run before any pattern's oracle/discovery/
validation stage, on `development`-split rows only)

For every feature or derived decision-time atom named in §5, restricted to the relevant development
partition (`D_F` or `D_M`, whichever scale is under test):

1. **Numeric/ordinal feature vs. binary outcome:** compute the point-biserial correlation between the
   feature and the outcome indicator. **Flag** if `|r| >= 0.95`.
2. **Categorical feature (including a derived boolean) vs. binary outcome:** compute Cramér's V
   between the feature and the outcome indicator. **Flag** if `V >= 0.95`.
3. **The rule's own exposed/unexposed partition specifically:** compute the outcome rate inside the
   rule's exposed group and outside it. **Flag** if either group is `>= 99%` pure on the outcome
   (i.e., the rule is functioning as a near-perfect single-threshold classifier of the outcome
   itself) — this is the exact shape of the second same-day defect (`total_quantity < 2` was 100%
   true for cancellations).

**Consequence of a flag, fixed now:** a flagged feature is excluded from that pattern's candidate
feature set before `discover_candidates()` or any oracle computation runs for it. The exclusion, the
triggering statistic, and which check fired are appended to §12 as a dated correction note. **The
pattern's rule content and hypothesized direction are not rewritten to route around the exclusion**
— if the exclusion makes a pre-registered rule's exact condition unrepresentable, that pattern is
marked `EXCLUDED — LEAKAGE-BLOCKED` in §12 and is not scored in §7, per the same append-only,
no-silent-rewrite discipline `TASK-099`'s message specifies. No flag has been evaluated yet; §4.1 is
the only part of this check performed before the freeze commit, precisely because §4.2 requires
outcome-conditional computation on real rows, which item 3's own text requires be run and recorded
mechanically, never argued away in advance.

---

## 5. Item 4 — Pre-registered target-pattern hypotheses (frozen before any data is opened)

Two outcomes, both realized strictly after the decision (order placement) and both defined without
using any column named as a candidate feature below.

### 5.1 Outcomes

**`OUTCOME_LATE`** — binary, `higher_is_worse=True`, `aggregation_rule="rate"`, `unit="rate"`.
- **Definition:** `1` if `order_delivered_customer_date > order_estimated_delivery_date`, else `0`.
- **Eligibility cohort:** rows of `F` where both `order_delivered_customer_date` and
  `order_estimated_delivery_date` are non-null (i.e., an actual delivery is recorded). Rows outside
  this cohort are excluded from every `OUTCOME_LATE` computation, not imputed.
- **Source columns:** both from `olist_orders_dataset` only.

**`OUTCOME_LOW_REVIEW`** — binary, `higher_is_worse=True`, `aggregation_rule="rate"`, `unit="rate"`.
- **Definition:** `1` if `review_score <= P25(review_score | development split, that scale)`, else
  `0`. The cut is defined **relative to the development split's own distribution**, computed
  mechanically in §12 once data opens, using `polars.Series.quantile(0.25, interpolation="linear")`
  — the same interpolation convention `discovery.engine`'s own `numeric_quantiles` grid uses — so no
  assumption about `review_score`'s actual scale (1–5, 1–10, or otherwise) is baked into this
  document.
- **Eligibility cohort:** rows of `F` with a non-null `review_score` (i.e., a review exists).
- **Source column:** `review_score`, from `olist_order_reviews_dataset` only.

### 5.2 Derived decision-time atom (one, disclosed)

**`seller_customer_cross_state`** = `1` if `seller_state != customer_state` (both non-null), else
`0`. Both inputs are attributes of already-existing parties (the seller and the customer), known at
order-placement time, independent of anything that happens afterward; their inequality is computed
from decision-time information only, using no outcome data — the same class of legitimate
decision-time derivation `travel_month` was (a calendar decomposition of a decision-time date,
`HANDOFF-059`/`ADR-047`), disclosed here rather than left implicit. This column is added to the
analytical frame once, identically, at both scales, before `discover_candidates()` runs; it is never
constructed from or conditioned on `OUTCOME_LATE`/`OUTCOME_LOW_REVIEW`.

### 5.3 The four pre-registered patterns

Each stated as a specific, checkable rule with a committed direction (condition → **higher** rate of
a harmful binary outcome), reasoned from column semantics and generic marketplace-logistics
plausibility alone — no Olist row, distribution, or outcome value was consulted to write any of the
four.

| ID | Candidate feature(s) (expected `TASK-008` classification, from reading the classifier's own rules in §1 — not verified against this dataset yet) | Rule | Outcome | Hypothesized direction |
|---|---|---|---|---|
| **OL01** | `seller_customer_cross_state` (derived; both inputs expected `DECISION_TIME` — string, low-cardinality categorical, matches `feature_timing.classify_feature_timing`'s `semantic_type_guess == "categorical"` rule) | `seller_customer_cross_state == 1` | `OUTCOME_LATE` | Cross-state shipping increases the late-delivery rate (more logistics legs, more failure points), vs. same-state shipping. |
| **OL02** | `max_installments` (expected `DECISION_TIME` — the raw column name token `installments` is a literal member of `feature_timing._DECISION_TIME_COUNT_HINTS`) | `max_installments >= P75(max_installments \| development split, that scale)` | `OUTCOME_LOW_REVIEW` | Orders paid in an unusually high number of installments show a higher low-review rate than orders below that quartile, vs. below it. |
| **OL03** | `modal_payment_type` (expected `DECISION_TIME` — string, low-cardinality categorical) | `modal_payment_type != \text{mode}(modal\_payment\_type \mid \text{development split, that scale})` (i.e., any non-default payment method, pooled as one group) | `OUTCOME_LOW_REVIEW` | Orders paid by a non-default payment method (whatever the single most common category turns out to be) show a higher low-review rate than orders paid by the default/most-common method. |
| **OL04** | `product_category_name` (expected `DECISION_TIME` — string; `product_category_name_translation.csv`'s own 70-row size, already given in the schema dump, bounds this column to at most 70 distinct values against tens of thousands of order rows, i.e. unambiguously low-cardinality by the numbers already in hand, no data opened to establish this) | `product_category_name != \text{mode}(product\_category\_name \mid \text{development split, that scale})` (i.e., the long tail outside the single highest-volume category, pooled) | `OUTCOME_LATE` | Orders outside the single highest-volume product category show a higher late-delivery rate than orders inside it (higher-volume categories are hypothesized to have more logistics attention/optimization). |

**Tie-break rule, fixed for every "mode"/frequency-rank reference above:** the category with the
strictly largest development-split row count; if two or more categories tie for the largest count,
the one that is lexicographically first (ascending, case-sensitive on the raw string) is the mode.
This is decided now so no session ever has discretion to pick a "more favorable" tie-break after
seeing the actual counts.

**What would falsify each pattern, stated so it is checkable, not just directional:** at either
scale, a pattern **fails to replicate its own hypothesized direction** if the observed
exposed-vs-comparison effect (§7.1) has the *opposite* sign from the direction stated above. A
sign-flip is recorded as such in §12/§7's results table, not silently dropped — a wrong-signed result
is real, disclosed evidence against the hypothesis, exactly as the interpretation branches in §9
require for a promoted finding with the wrong direction.

**Explicitly not pre-registered, and why:** no hypothesis conditions on `price`, `total_freight_value`,
or any raw amount alone (e.g., "expensive orders are more/less likely to be late") — every travel/
b2b_sales/ecommerce true-pattern precedent conditions on a *behavioral or structural* choice, not a
bare price level, and a bare-price rule risks exactly the kind of "obvious, non-actionable"
tautology-adjacent finding `memory/CURRENT_STATE.md`'s "Kill signal" language already warns against
(large orders cost more, restated). `product_weight_g` and `freight_value` are deliberately not used
as primary candidate features: reading `feature_timing`'s own disclosed rules in §1, neither column
name matches any positive `DECISION_TIME` rule (`freight_value`'s tokens `{freight, value}` match no
`_QUOTED_AMOUNT_NAME_HINTS`/`_CURRENCY_NAME_HINTS` entry; `product_weight_g`'s tokens match no count/
flag/amount hint either) — both are anticipated, from the classifier's own public code alone, to
classify `UNKNOWN`, which `TASK-008`'s own documented "known limitation, not a defect" already
anticipates as requiring human resolution this experiment does not perform. This anticipation is
disclosed now, before the freeze commit, precisely so a genuinely `UNKNOWN` result in §12 is
confirmation of a stated prediction, not a surprise requiring hypothesis-content rework.

---

## 6. Item 5 — The three-stage comparison, frozen in advance, per pattern, per scale

Run identically for each of `OL01`–`OL04` (minus any marked `EXCLUDED — LEAKAGE-BLOCKED` per §4.2),
at the full-scale condition (`D_F`) and the matched-scale condition (`D_M`), in this fixed order —
**Stage 1's multiplicity sub-step depends on a scalar from Stage 2, as disclosed in §6.1, so Stage 2
runs first; nothing about Stage 1 bypassing search for *candidate identification* is affected by
that ordering, only the multiplicity denominator borrows a number from it.**

### 6.1 Stage 1 — Oracle detectability (the pre-registered rule, handed directly to the gates' own
formulas, search bypassed for candidate identification)

The same method `docs/benchmark/task-069-validation-power-autopsy.md` §3 already established as
this project's oracle methodology, reused verbatim, not redesigned:

1. Compute the rule's exact exposed row set within the relevant development table (`D_F` or `D_M`)
   — `n_exposed`. Comparison group = every development-split row **not** satisfying the rule,
   restricted to the pattern's own outcome-eligibility cohort (§5.1) — `n_comparison`.
2. Compute the outcome rate inside the exposed group and inside the comparison group; the raw
   effect is their difference, signed by `harm_multiplier` (`higher_is_worse=True` for both outcomes
   here, so a positive difference is harmful, matching §5.3's stated directions).
3. Compute `pooled_sd` for a binary 0/1 outcome as `sqrt(p_pooled * (1 - p_pooled))`, `p_pooled`
   being the outcome rate over the pooled exposed+comparison cohort — the standard pooled-proportion
   variance, not a new formula invented for this document.
4. Call `minimum_detectable_effect(n_exposed, n_comparison, pooled_sd)` — `validation.apply`'s own
   real, unmodified function (**G03**'s formula) — to get `MDE80`. Compare `MDE80` to the observed
   `|effect|`.
5. Compute a p-value for the observed effect via a two-proportion z-test using an **unclustered**
   standard error — deliberately optimistic, the same one-directional bound `task-069-validation-
   power-autopsy.md` §3 used ("clustering... can only widen the interval," so this is a lower bound
   on the real contract's p-value, used only to show when even the most generous bound cannot clear
   the bar — never to claim a tighter bound than the real clustered estimate would give). Olist's own
   natural cluster key is `customer_unique_id` (a repeat-customer identifier, the direct analogue of
   travel's `customer_id`); the real, clustered estimate is *not* computed in Stage 1, by design,
   matching the autopsy's own deliberate asymmetry.
6. **Multiplicity denominator.** Call `benjamini_hochberg_adjusted([p_value], family_size=F)` —
   `validation.grading`'s own real, unmodified function (**G05**'s formula) — where `F` is the real
   `evaluated_hypotheses` count `discover_candidates()` actually reports for that scale in Stage 2
   below (**not** an assumed or invented number). This mirrors `task-069-validation-power-
   autopsy.md`'s own oracle bound exactly: its `family_size = 26,213` was the real evaluated-
   hypothesis count of the actual committed search it was auditing, not a hypothetical figure.
   Borrowing this one scalar from Stage 2 does not let Stage 2's *candidates* influence Stage 1's
   *rule* — the rule and its exposed rows are fixed by §5 alone.
7. **Structural floors, checked directly against `ValidationThresholds` (contract `v1.3.0`, unmodified):**
   `n_exposed >= min_exposed_records` (50) and, since both outcomes here are binary,
   `outcome_events_in_exposed_group >= min_outcome_events_binary` (25) — read from `contract.py`
   exactly as currently shipped, not redefined.
8. **Detectability verdict** per pattern per scale: `DETECTABLE` iff every floor in step 7 is
   cleared, `MDE80 <= |effect|`, and the BH-adjusted p-value `<= fdr_alpha` (0.10). Otherwise
   `NOT_DETECTABLE`, with the specific binding reason recorded (which check failed, by how much —
   the same "×short" framing `task-069-validation-power-autopsy.md` Table 2 uses), not just a
   pass/fail flag.

### 6.2 Stage 2 — Actual discovery

Run the real, unmodified `discover_candidates(frame, feature_columns, outcome, config=DiscoveryConfig())`
— every `DiscoveryConfig` field at its current committed default (`seed=1729`, `min_support=0.01`,
`max_support=0.40`, `min_n=40`, `max_conditions=3`, `beam_width=80`, `beam_rules_per_structure=2`,
`max_expansion_beam_size=512`, `top_k=15`, `numeric_quantiles=(0.2,0.4,0.6,0.8)`,
`max_categorical_levels=12`, `max_candidate_jaccard=0.85`, `max_candidates_per_atom=5`,
`population_score_exponent=0.5`, `diversity_discount_weight=0.5`,
`min_diversity_relevance_ratio` and other selection knobs at their current shipped values) — **no
knob is changed for this experiment, per `TASK-099`'s own explicit exclusion of any gate/threshold/
engine change.** `feature_columns` is whatever `classify_columns()` (§3) actually labeled
`DECISION_TIME`, minus anything `§4.2` flags. Run once per outcome actually used by a
still-in-scope pattern (`OUTCOME_LATE`, `OUTCOME_LOW_REVIEW`), once per scale — four runs total
unless a pattern is excluded.

**Matching (reused, not reinvented):** for each pattern, its own rule's exposed-row-id set is treated
exactly as `scripts/evaluate_benchmark.py` treats a ground-truth pattern's `affected_*_ids` — a
Stage-2 candidate **matches** the pattern iff
`|candidate_exposed_ids ∩ pattern_exposed_ids| / |pattern_exposed_ids| >= MATCH_RECALL_THRESHOLD`
(`0.5`, the exact constant `scripts/evaluate_benchmark.py` already uses, not a new threshold chosen
for this document). Record, per pattern per scale: whether any Top-K candidate matches
(`FOUND`/`NOT_FOUND`), and if found, which candidate id and its recall against the pattern.

### 6.3 Stage 3 — Validated/promoted discovery

Run the real, unmodified `validation.apply.run_validation(...)` (all gates, contract `v1.3.0` as
currently shipped) against **every** Top-K candidate Stage 2 produced at that scale — the same
"validate the whole committed set" scope `TASK-019` uses for every official run, not a
cherry-picked subset — then read off, specifically for each pattern's matched candidate (if any):
evidence level reached, the full gate pass/fail profile, and whether it clears to
`predictive_association` or above. Also report, across the *entire* validated Top-K set at that
scale (matched or not): any wrong-direction promotion above the materiality threshold, and the same
G06/G12/G13/G14 pass-rate summary `docs/benchmark/task-069-validation-power-autopsy.md` §4 reports,
for general safety context.

**Disclosed structural difference from the travel/b2b_sales/ecommerce precedent, stated honestly
rather than glossed over:** those three domains are synthetic, with an injected, labeled ground-truth
file (`hidden_ground_truth.json`) naming both true patterns *and* adversarial confounding traps.
Olist has neither — it is real, unlabeled data, and §5's four patterns are this experiment's own
hypotheses, not a planted ground truth. There is therefore **no trap-rejection metric** to compute
here in the `decision-gate.md` sense (no trap exists to reject or wrongly promote). "Precision/
safety" in this experiment is operationalized as: does any candidate, matched or not, get promoted
with the wrong sign above materiality, and do the same robustness/confounding gates (G06, G12) that
would catch a spurious finding on synthetic data behave the same way here — a narrower, honestly
weaker safety signal than a labeled-trap benchmark provides, disclosed here so it is not later
mistaken for the stronger claim.

---

## 7. Item 6 — Blindness caveat, cited exactly, not glossed over

This document's hypotheses (§5) were drafted using **only**: the schema/row-count dump reproduced in
§2.1, the three named public facts about the dataset's design, and this project's own source code
(not Olist data). No Olist row, distribution, correlation, or outcome value was opened before this
document's freeze commit (§1's process log; §13 records the commit hash). Every numeric threshold in
§5 is defined relative to the data's own distribution (a percentile, a frequency rank), computed
mechanically only after the freeze, specifically so no author's prior general knowledge of this
well-known public dataset's actual category values or typical findings could bias a threshold choice
— a stricter posture than `TASK-099` item 6 requires for a dataset whose columns had already been
inspected in a prior session (this document's situation is the "prefer a genuinely fresh dataset"
branch item 6 names, not the "argue the caveat" branch `task-068`-style reuse would have required),
because the schema dump this session received was deliberately restricted to headers and row counts
only, by the orchestrator, before this session ever started.

**What could still bias this document despite the above, disclosed rather than dismissed:** general
pretrained familiarity with "Olist" as a well-known Kaggle dataset could in principle have supplied
unstated priors about its typical column value ranges or commonly-reported findings (e.g., its
well-known review-score/delivery-delay relationship discussed in public tutorials). This document
deliberately avoided asserting any such specific fact — no hypothesis in §5 names a concrete category
value, an assumed scale (e.g., "1–5"), or an effect direction sourced from any recollection of a
public analysis of this dataset — but a reviewer who believes this dataset is *too* well-known for
any drafting session to be genuinely naive about it should treat that as a real, disclosed limitation
of this pre-registration, not a claim this document makes and then hides. The four hypotheses in §5
are constructed so that even a maximally-informed prior about "late delivery" and "low review score"
being plausible marketplace harms — an extremely generic e-commerce intuition, not specific to this
dataset's actual numbers — is the most such a prior could have contributed; no rule threshold or
outcome cutoff is fixed to a specific already-known value.

---

## 8. Decision-gate binding — retained unmodified

No gate, threshold, or estimator is changed by this document, matching `TASK-099`'s explicit scope
exclusion. `contract.py`'s `ValidationThresholds` (v1.3.0, as currently shipped) and `DiscoveryConfig`'s
current committed defaults apply exactly as they do to every other domain. `docs/benchmark/
decision-gate.md` is not edited by this document and is not the scoring instrument for this
experiment in any case — §6's three-stage comparison, not the decision-gate bands, is what this
experiment's own success/failure is read against, per §9's frozen interpretation below.

---

## 9. Item 7 — Interpretation, frozen verbatim from `TASK-099`'s own `TASKS.md` entry

Reproduced exactly as written there, not paraphrased, not reordered:

> - Oracle detectability rises **and** actual recall rises at the larger scale → strong evidence the
>   current travel recall ceiling is substantially sample-size driven.
> - Oracle detectability rises but actual recall does **not** → a genuine search/discovery gap, worth
>   engineering — name it specifically, do not generalize past what was actually found.
> - Oracle detectability does **not** materially rise despite much more data → raw row count is not
>   the operative constraint; effect prevalence, effect size, multiplicity correction, or
>   benchmark/target-pattern construction itself needs examination next — not another data-volume
>   attempt.
> - Precision or safety deteriorates while recall rises → report this explicitly as a **trade-off**,
>   never as an unqualified improvement.

These four branches are not mutually exclusive across `OL01`–`OL04` — different patterns may land in
different branches at the same scale, and the eventual results record must say so per-pattern rather
than force one overall verdict, exactly as `ADR-092`'s own per-pattern (not aggregate) treatment of
travel's seven patterns already established as this project's norm.

---

## 10. What may not change after this document's freeze commit

Fixed and closed to silent edit, per `TASK-099`'s own hard rule ("no pre-registered target pattern,
feature choice, or acceptance criterion may be written, or silently adjusted, with knowledge of how
the actual experiment would come out"):

- §2 (join specification, decision timestamp, split-tool choice, downsample method, seed, row
  target);
- §3 (which classification path is used, and that hand-built feature roles are never substituted);
- §4 (the leakage-check method and its consequence rule);
- §5 (all four hypotheses' feature choices, rules, outcomes, and directions — including the tie-break
  rule and the explicit non-use of `price`/`freight_value`/`product_weight_g`);
- §6 (the three-stage protocol, the matching threshold, the multiplicity family-size method);
- §9 (the interpretation branches, verbatim).

**Explicitly permitted after the freeze commit, append-only, dated:** §12 below, for exactly the
three classes of content `TASK-099`'s process discipline names — the mechanical join/row-count
results (§2.2's numeric output), the real `classify_columns()` output per column (§3), and the §4.2
leakage-audit statistics and any resulting `EXCLUDED — LEAKAGE-BLOCKED` marks. If any of these
reveals a hypothesis was structurally unworkable (a named column does not survive the join, or a
named feature does not classify `DECISION_TIME`, or a feature is leakage-blocked), the correction is
recorded as a visible, dated note in §12 — **the hypothesis's rule content and direction are not
silently reworded to route around the finding.** A hypothesis that cannot be run as specified is
marked `EXCLUDED` with the reason, not repaired.

---

## 11. Explicitly out of scope (restated from `TASK-099` and the assigning message, not narrowed)

This document does not run `discover_candidates()`, the validation pipeline, or any outcome-
conditional analysis. It changes no gate, threshold, estimator, or `discovery.engine` logic. It does
not touch `TASK-096`. It performs no customer/business/accelerator outreach. Running §6's protocol is
a separate, later task, to be opened only after independent review confirms this document is a
genuine, falsifiable freeze — matching `TASK-074`/`TASK-068`'s own preregistration-first precedent
`TASK-099` explicitly cites.

---

## 12. Post-freeze mechanical amendments

*(Empty at freeze time. To be appended, dated, after this document's freeze commit, containing only:
§2.2's real join row counts and confirmed post-join column names; §3's real `classify_columns()`
output for every column reaching the joined frame; §4.2's leakage-audit statistics per candidate
feature and any resulting `EXCLUDED — LEAKAGE-BLOCKED` marks; and any other purely mechanical
correction the process discipline in §10 permits. No hypothesis content, threshold definition, or
interpretation branch may be added, removed, or reworded here.)*

---

## 13. Freeze record

This document's first commit to this worktree branch (`worktree-agent-a52ffa27a909bad45`) is the
pre-registration freeze point `TASK-099`'s process discipline requires. That commit's hash, and
confirmation that it touches only this file, is reported by the session that authored it, in its
handoff to the orchestrator — not written into this file itself, to avoid the obvious chicken-and-egg
problem of a file recording its own not-yet-created commit hash. Any session reviewing this document
should verify the freeze claim directly: `git log --follow -- docs/benchmark/
task-099-sample-size-detectability-preregistration.md` should show exactly one commit before any
`§12` amendment exists, and that commit's diff should be this file's initial version, added, nothing
else.
