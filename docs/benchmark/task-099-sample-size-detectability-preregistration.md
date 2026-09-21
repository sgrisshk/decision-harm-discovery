# TASK-099 — Sample-size / statistical-detectability pre-registration (real public data, Olist)

**Owner:** STATISTICS
**Recorded:** 2026-09-21
**Status:** PRE-REGISTERED, ROUND 2 REVISION (2026-09-21). **This document produces no data, runs no
discovery, runs no validation.** It specifies a design only. A dated freeze-point commit (this file's
first commit to this worktree branch) is the actual pre-registration event; everything above the line
marked "§12 Post-freeze mechanical amendments" was written and committed before a single row of the
target dataset was loaded. Running the experiment this document specifies is a separate, later task
(`TASK-099`'s own text: "opened only once this document is independently confirmed to actually
pre-register the design"), not performed here.

**2026-09-21 ROUND 2 REVISION banner, read this first.** Round 1 independent adversarial
`CODE_REVIEWER` review (`TASKS.md` `TASK-099` entry, "Review verdict") returned **APPROVED WITH
REVISION NEEDED** — not structural, matching this project's own `TASK-095` round-1→2 precedent, not a
rejection. One material, previously-undisclosed gap (Finding F, §2.3's false claim about the temporal-
split tooling's "default configuration") and one minor finding (§5.2's derived-atom classification
ordering) required revision; two further points (Stage-1/Stage-2 execution ordering, and the
well-known-dataset prior-knowledge risk) required an explicit response, not a rewrite. Full accounting
in new **§14 (Revision log, round 1 → round 2)** at the end of this document. **This revision touches
only §2.3, §5.2, §6 (a new execution-order requirement), and §7 (a strengthened blindness
disclosure) — every other section, including all four hypotheses (`OL01`–`OL04`), the matched-scale
dev-only downsample design, the `TASK-008` foreknowledge handling, the code-reuse citations, and §9's
verbatim interpretation branches, is unchanged from the round-1 freeze.** This revision is itself
performed under the same blindness discipline as the original freeze: no Olist data row was opened to
produce it (see §14's own confirmation). This document still does not mark itself `APPROVED`; that
determination belongs to the round 2 independent adversarial `CODE_REVIEWER` pass this revision now
requests — matching `TASK-099`'s own explicit instruction that only a round-2 reviewer, not the
implementer, may authorize execution.

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

### 2.3 Decision timestamp and temporal split — **revised 2026-09-21, Finding F (§14)**

**Round-1 text corrected here.** The round-1 version of this section claimed Olist's split boundaries
would come from "that tool's existing, unmodified default configuration." Round-1 independent review
checked this against the actual code and found it false, and this revision confirms the same reading
independently before writing the fix: `scripts/build_domain_temporal_splits.py` takes a `--domain`
argument that must already be a key of `domain_benchmarks.registry.DOMAIN_REGISTRY`, and for every
registered domain it builds the split purely from that domain's own `DomainSpec.development_end` /
`.validation_end` / `.future_holdout_end` — three **required, non-defaulted** string fields
(`policy_analytics/domain_benchmarks/common.py` `DomainSpec`, lines ~113-115). Reading
`packages/analytics/src/policy_analytics/domain_benchmarks/ecommerce.py` directly (module-level
constants, lines 28-30) confirms it hand-authors `DEVELOPMENT_END = "2024-12-31"`,
`VALIDATION_END = "2025-06-30"`, `FUTURE_HOLDOUT_END = "2025-12-31"` — specific calendar dates chosen
for that domain, not read from any shared default. `policy_analytics/domain_benchmarks/
analytical_bridge.py`'s `temporal_split_config(spec)` (lines 73-88) does nothing but copy those three
fields verbatim into a `TemporalSplitConfig`. The only place anything resembling a "default" exists is
`policy_analytics/temporal_splits.py`'s `TemporalSplitConfig` dataclass, whose field defaults
(`development_end="2024-12-31"`, `validation_end="2025-06-30"`, `future_holdout_end="2025-12-31"`,
lines 24-29) are **travel's own specific historical dates**, not a generic proportion rule — and every
domain overrides them explicitly via its own `DomainSpec` regardless. Olist has no `DomainSpec` entry
in `DOMAIN_REGISTRY` at all, so there is no fallback of any kind for it to inherit. This confirms
Finding F exactly as recorded in `TASKS.md`: the round-1 claim described tooling that does not exist.

**The fix — a principled, data-relative split rule, pre-registered now, not deferred.** Two things are
separated: the **proportions** this project already uses (a real, reusable convention, not invented for
this experiment), and the **specific dates**, which round 1 correctly identifies must not be hand-picked
for Olist. Both travel's own `TemporalSplitConfig` defaults and `ecommerce.py`'s explicit dates cover
the identical shape — 12 months development / 6 months validation / 6 months future_holdout, i.e.
**50% / 25% / 25%** of a 24-month covered range — confirmed identical across both by direct inspection,
not assumed from one example. This document adopts that same 50/25/25 proportion, but applies it as
**percentile cutoffs of Olist's own real `order_purchase_timestamp` distribution** rather than as
fixed calendar dates — the same "define relative to the data itself" convention §5.1's
`OUTCOME_LOW_REVIEW` threshold already uses, now applied consistently to the split boundaries too, so
neither is a number chosen with foreknowledge of Olist's actual date range:

1. Let `t_min` = the minimum and `t_max` = the maximum `order_purchase_timestamp` date (day precision,
   time-of-day dropped) over all of `F`.
2. `development_start = t_min`. `development_end` = the date at the **50th percentile**
   (`polars.Series.quantile(0.50, interpolation="linear")`, the identical interpolation convention
   `OUTCOME_LOW_REVIEW`'s `P25` already uses, for consistency) of `F`'s `order_purchase_timestamp`
   values, truncated to a date.
3. `validation_start` = the day immediately following `development_end`. `validation_end` = the date
   at the **75th percentile** of the same distribution, same interpolation, truncated to a date.
4. `future_holdout_start` = the day immediately following `validation_end`. `future_holdout_end` =
   `t_max` (i.e., the last row's own date — not a percentile computation, so every row of `F` is
   assigned to exactly one split with none left over past the boundary).
5. All five boundary dates are **mechanical, pre-determined functions of whatever `F`'s real date
   range turns out to be** — computed only in §12, after data opens, never chosen by this document.
   Reviewer note: because `order_purchase_timestamp` is what §5.1/§5.3 already establish as this
   dataset's own decision timestamp, a percentile of its distribution is, by construction, a
   row-count-based split (not exactly a calendar-time split) — a **stronger**, not weaker, match to
   "50/25/25 of the data" than the calendar-date convention it replaces, since a calendar-date cutoff
   on real (non-uniform) order volume would not generally land at exactly 50/25/25 by row count.

**Mechanics — the real, unmodified split-assignment function, called directly.** Olist cannot go
through `scripts/build_domain_temporal_splits.py`'s own `--domain` CLI (it requires `DOMAIN_REGISTRY`
membership, and registering Olist as a new `DomainSpec` — a synthetic-domain benchmark construct with
patterns/traps/a row generator — is not this experiment's scope and is not proposed here). Instead,
this document calls the same underlying, real, unmodified function every domain's manifest is actually
built from: `policy_analytics.temporal_splits.assign_temporal_splits` (and, if a full manifest is
wanted for parity with the other domains, `build_temporal_split_manifest`), passing a manually
constructed `TemporalSplitConfig(version="olist-temporal-split-v1.0.0",
timestamp_column="order_purchase_timestamp", identifier_column="order_id",
development_start=..., development_end=..., validation_start=..., validation_end=...,
future_holdout_start=..., future_holdout_end=..., assignment_rule="closed intervals on
order_purchase_timestamp; no random shuffle", outcome_availability_mode="CLOSED_SYNTHETIC_BENCHMARK")`
with the five dates computed per steps 1-4 above. **Disclosed, checked infelicity:** `_validate_config`
(`temporal_splits.py` lines 47-52) raises `ValueError` unless `outcome_availability_mode` is literally
the string `"CLOSED_SYNTHETIC_BENCHMARK"` — the only value it currently accepts. Despite the name, its
actual, documented meaning (`build_temporal_split_manifest`'s own `"basis"` text, lines 186-189) is
"the dataset is closed and every row's outcome is already final, no right-censoring" — a real property
of a static, historical Kaggle export like Olist, not an assertion that Olist is synthetic data. This
document reuses the tool's only supported mode literal for that reason, disclosed explicitly rather
than silently relying on a misleading string; it changes nothing about how the boundaries themselves
are computed. `F` is sorted ascending by `order_purchase_timestamp` (deterministic, no randomness)
before assignment, as in the round-1 text. Call the resulting full-scale development partition `D_F`.

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

### 5.2 Derived decision-time atom (one, disclosed) — **revised 2026-09-21, minor finding (§14)**

**`seller_customer_cross_state`** = `1` if `seller_state != customer_state` (both non-null), else
`0`. Both inputs are attributes of already-existing parties (the seller and the customer), known at
order-placement time, independent of anything that happens afterward; their inequality is computed
from decision-time information only, using no outcome data.

**Round-1 gap, and why this document does not choose the "preferred" option.** Round 1 correctly found
that the round-1 text never specified whether this atom is added before or after §3's real
`classify_columns()` step, and offered two resolutions: (a) add it before CSV export so
`classify_columns()` labels it like any other column (preferred, if mechanically sound), or (b) an
explicit, disclosed exception mirroring `travel_month`. This revision traced (a) against the actual
classifier code, as the review instructed, rather than assuming it would work, and found **it does
not**: under §3's own fidelity requirement (`pl.read_csv(path, infer_schema_length=0)`, all columns
read as strings), a two-valued `"0"`/`"1"` column is recognized by `schema_profiler._guess_semantic_type`
(lines 160-161) as `semantic_type_guess == "boolean_flag"` — a **different** string than
`"categorical"`. `feature_timing.classify_feature_timing`'s only positive DECISION_TIME rule matching
on semantic type checks `profile.semantic_type_guess == "categorical"` literally (line 182); it does
not match `"boolean_flag"`. None of `seller_customer_cross_state`'s name tokens (`seller`, `customer`,
`cross`, `state`) appear in `_DECISION_TIME_COUNT_HINTS`, `_DECISION_TIME_FLAG_HINTS`, or the
quoted-amount hint sets (lines 101-117) either. Tracing the full rule chain in `classify_feature_timing`
(lines 135-212), this column falls through every positive rule and lands on the final catch-all —
`FeatureTiming.UNKNOWN`, "no rule matched; requires explicit human classification" — regardless of
whether it is added before or after CSV export (the outcome is a function of the column's *value
content*, not of *when* it is added; export timing does not change it). Per §3's own binding rule,
`UNKNOWN` is excluded from `discover_candidates()`'s feature set — so option (a), applied naively,
would silently break `OL01`'s premise rather than validate it. This is disclosed here precisely
because it is the kind of check the round-1 review asked this revision to perform directly rather than
assert as plausible.

**Resolution: option (b), an explicit, disclosed exception — the same shape `travel_month` actually
used.** Checking the precedent directly (`memory/HANDOFFS.md` `HANDOFF-059`) rather than assuming the
analogy holds: `travel_month` (an integer 1-12 calendar decomposition) is not organically labeled
`DECISION_TIME` by `classify_columns()`'s generic name-matching rules either — no token in `{travel,
month}` matches any positive rule, and an integer-typed column never reaches the `"categorical"`
branch at all (that branch requires `inferred_type == "string"`). `travel_month`'s real `DECISION_TIME`
status is instead delivered as an **explicit, disclosed, declared-feature-timing lineage**, propagated
through `blind/allowlist.yaml` and `tools/blind_agent/models.py` rather than produced by the generic
classifier — exactly the shape option (b) describes. This document adopts the identical resolution for
`seller_customer_cross_state`: it is **declared `DECISION_TIME` by explicit statement in this
document, not by relying on `classify_columns()`'s own output for this one column.** This is narrower
than it may first appear — the exception covers only this one derived column's own label; it does not
touch `§3`'s binding rule for anything else. Concretely:

- `seller_state` and `customer_state` — the atom's two *inputs* — are **not** exceptions: they must
  still independently clear the real `classify_columns()` call and be confirmed `DECISION_TIME` in
  §12, exactly as every other candidate feature in §5.3 must be. (Expectation, not yet verified: both
  are low-cardinality string columns — Brazilian state codes, at most ~27 distinct values against tens
  of thousands of rows — so each is independently expected to hit the ordinary `"categorical"` rule on
  its own terms, unlike their boolean-valued combination.)
- `seller_customer_cross_state` itself is added to the analytical frame once, identically, at both
  scales, immediately after the joins in §2.2 (i.e., it is present in the CSV that is exported and fed
  to `profile_columns()`/`classify_columns()` in §3, so a reviewer can see its real, actual classifier
  output too) — but its membership in `OL01`'s feature set is authorized by this document's explicit
  declaration, not conditioned on what `classify_columns()` happens to return for it. If the real run's
  `classify_columns()` output for this column is anything other than `UNKNOWN` or `DECISION_TIME` (an
  outcome this document does not currently expect, given the trace above), that surprising result is
  recorded in §12 as a disclosed mechanical finding, not silently reconciled either way.
- This exception is never constructed from or conditioned on `OUTCOME_LATE`/`OUTCOME_LOW_REVIEW` — its
  derivation (an inequality of two already-decision-time-classified party attributes) is fixed here,
  before any data is opened, precisely so declaring it `DECISION_TIME` is a disclosed process choice
  about classifier coverage, never a route around the leakage/timing discipline §3-§4 establish for
  everything else.

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

### 6.0 Execution-order requirement, binding — **added 2026-09-21, response to review point 3 (§14)**

Round 1 confirmed Stage 1 borrowing its multiplicity family size from Stage 2's own
`evaluated_hypotheses` count (§6.1 step 6 below) is mechanistically sound, mirroring
`task-069-validation-power-autopsy.md`'s own precedent exactly. It flagged a real execution-discipline
risk distinct from that mechanism: `task-069`'s own oracle bound reused an **already-frozen, historical**
`evaluated_hypotheses` count from a run that had already completed and been committed before that
autopsy was written. Here, by contrast, §4.2's leakage audit, Stage 1, and Stage 2 are all intended to
run in **one uninterrupted session**, with no prior frozen run to borrow from — creating a real,
previously-unstated path by which a session could (even unintentionally) look at Stage 1's own
detectability outcome for a pattern before finishing §4.2's leakage checks for that pattern's
features, and let that knowledge shape how a borderline leakage statistic gets read.

**Binding rule, closing that path:** for every pattern, at every scale, **§4.2's empirical determinism
audit must be run to completion and its result (pass, or which check flagged and the exact statistic)
recorded in §12 before that pattern's own Stage 1 oracle-detectability pass/fail verdict is computed or
inspected, by anyone, in that session.** Concretely: the executing session runs §4.2 for all four
patterns at a given scale first, records every flag/exclusion, and only then proceeds to §6.1 for the
patterns that survive it, at that same scale — never interleaved pattern-by-pattern in a way that lets
one pattern's Stage 1 result be visible while another pattern's §4.2 audit is still in progress. This
does not change §4.2's own consequence rule (a flagged feature is still excluded regardless of any
Stage 1 outcome, per §4.2's existing text) — it exists solely so that rule is never exercised, even
inadvertently, with knowledge of which patterns "need" a feature excluded to reach a particular
detectability verdict. A session that violates this ordering must disclose the violation in §12 rather
than silently proceed, per this document's existing append-only correction discipline (§10).

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

### 7.1 Hypothesis-*selection* risk, addressed squarely — **added 2026-09-21, response to review
point 5 (§14)**

Round 1 judged the residual well-known-dataset risk **more serious than the round-1 text above
credited**, and this revision responds to that directly rather than repeating the paragraph above with
softer wording. The round-1 text (and §1's process log) argues, and this revision does not withdraw,
that every **threshold** in §5 is data-relative and mechanically computed only after the freeze — that
argument is sound and unchanged. What it did not squarely address is a different question: not "is each
threshold blind," but **"was the choice of which two outcomes and which four feature/outcome pairings
were worth writing down in the first place, itself blind."**

Stated plainly, as the review asked: it cannot be fully ruled out. Olist is one of the most widely
published Kaggle datasets in existence, with numerous public notebooks and tutorials whose analyses
center on exactly `review_score`, delivery lateness, `payment_installments`, and cross-state shipping
as the dataset's own most-discussed relationships. A drafting session's generic, pretrained familiarity
with "these are the interesting columns in Olist" — even without recalling any specific number, and
even while genuinely never opening a row of this instance's data — could have shaped *which* four
candidate relationships felt worth pre-registering out of the much larger space `F`'s schema (§2.1)
actually offers (e.g., product dimensions, geolocation, seller/customer zip-prefix proximity, order
item count, freight-to-price ratio, and every other combination §5.3's own "explicitly not
pre-registered" paragraph does not individually rule out). This document does not, and after this
revision still does not, claim to be able to distinguish "these four patterns were chosen because they
are the most domain-plausible marketplace harms a naive analyst would write down from the schema alone"
from "these four patterns were chosen because this session has generic prior exposure to this specific,
famous dataset's own well-known public findings" — both produce the identical four hypotheses, and no
internal check available to this document can tell them apart after the fact.

**What this does and does not change.** The four hypotheses are not discarded: round 1 independently
confirmed they remain genuinely falsifiable (§5.3's explicit sign-flip/falsification criterion) and
that their thresholds are cleanly data-relative, and nothing about the selection-risk discussion above
weakens either property. What changes is only the document's own framing: it no longer implies that
hypothesis *selection* enjoys the same clean blindness argument §1/§7 make for threshold *mechanics*.
A round-2 reviewer, or the founder, weighing how much evidentiary weight to place on this experiment's
outcome should read `OL01`–`OL04` as patterns whose **thresholds** are rigorously blind and whose
**existence as the chosen four** carries a real, disclosed, un-removable residual prior-knowledge risk
— exactly the caveat `TASK-099` item 6 asks this document to address honestly rather than assert away,
now stated at the strength the round-1 review found warranted rather than the softer strength the
round-1 text originally gave it.

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
- §6 (the three-stage protocol, the matching threshold, the multiplicity family-size method,
  including new §6.0's execution-order requirement as of this revision);
- §9 (the interpretation branches, verbatim).

**This hard rule governs edits made *after* independent review approves this document and execution
begins — it does not forbid the kind of disclosed, reviewer-mandated revision pass this document has
just undergone (§14), which happened before any round-2 approval and before any data was opened,
matching `TASK-095`'s own round-1→2 precedent exactly: a real reviewer finding requires the original
author to revise, visibly and dated, not to leave the finding unaddressed on the theory that the
document is already "frozen." Once a round-2 reviewer approves this document, the rule above applies
in full and a further revision would require its own round 3.**

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

---

## 14. Revision log (round 1 → round 2)

This section exists so a round 2 reviewer can see exactly what changed without re-diffing the whole
document, matching `docs/analytics/task-095-k1-reservation-design.md` §14's own precedent for
recording a revision between review rounds — round 1 returned `APPROVED WITH REVISION NEEDED`, not a
rejection, so there is nothing here "REVOKED," only corrected and completed.

**Blindness confirmation for this revision itself, stated so it is checkable, not just asserted:** this
revision pass opened no Olist data — no CSV, no row, no summary statistic, no distribution. Everything
it changed was produced by reading this project's own already-public source code
(`scripts/build_domain_temporal_splits.py`, `policy_analytics/domain_benchmarks/common.py`,
`policy_analytics/domain_benchmarks/ecommerce.py`, `policy_analytics/domain_benchmarks/
analytical_bridge.py`, `policy_analytics/temporal_splits.py`, `policy_analytics/profiling/
schema_profiler.py`, `policy_analytics/profiling/feature_timing.py`) and this project's own prior
records (`TASKS.md`'s `TASK-099`/`TASK-095` entries, `memory/HANDOFFS.md`'s `HANDOFF-059`) — the same
"this project's own already-public code is not a data-blindness violation" boundary §1 already
established for the original freeze.

**Required revision 1 — Finding F, §2.3's false split-tooling claim.**
- **What changed:** §2.3 is rewritten. The false claim ("that tool's existing, unmodified default
  configuration") is corrected in place with a citation-backed account of how `DomainSpec`-based split
  boundaries actually work (hand-authored, required, non-defaulted per domain; no fallback; Olist has
  no `DomainSpec`). A new, principled, data-relative split rule is pre-registered: the project's own
  existing 50/25/25 development/validation/future_holdout proportion (confirmed identical across
  travel's `TemporalSplitConfig` defaults and `ecommerce.py`'s explicit dates), applied as percentile
  cutoffs (`P50`, `P75`, max) of Olist's own real `order_purchase_timestamp` distribution rather than
  as invented calendar dates — mirroring §5.1's own `OUTCOME_LOW_REVIEW` `P25` convention. Mechanics
  are specified down to which real function is called (`policy_analytics.temporal_splits.
  assign_temporal_splits`/`build_temporal_split_manifest`, called directly with a manually constructed
  `TemporalSplitConfig`, not via the domain-registry-gated CLI) and a disclosed note on the
  `outcome_availability_mode="CLOSED_SYNTHETIC_BENCHMARK"` literal's real meaning versus its name.
- **Why:** round 1 independently checked `scripts/build_domain_temporal_splits.py` and
  `ecommerce.py` directly and found the round-1 claim false — every domain's split boundaries are
  hand-authored, per-domain constants, with no generic fallback a new domain could inherit. Left
  uncorrected, this was an open, undisclosed discretionary knob directly determining every stage's
  statistical power — exactly the class of post-freeze wiggle room the rest of the document goes to
  unusual lengths to close, per the review's own framing.
- **What did NOT change:** the decision that a temporal split (rather than a non-temporal one) is used
  at all; the join specification (§2.2); the downsample method, seed, and row target (§2.5); the
  `validation`/`future_holdout` partitions being held fixed and un-downsampled across both scale
  conditions (§2.5) — none of this was implicated by Finding F and none of it is touched here.

**Required revision 2 — minor finding, §5.2's derived-atom classification ordering.**
- **What changed:** §5.2 is rewritten. Rather than assuming the "preferred" option (add the atom
  before CSV export, let `classify_columns()` label it) would work, this revision traced
  `schema_profiler._guess_semantic_type` and `feature_timing.classify_feature_timing`'s actual rule
  chain for a `"0"`/`"1"`-valued derived column and found it would be classified `semantic_type_guess
  == "boolean_flag"` (not `"categorical"`) and would match no other positive `DECISION_TIME` rule,
  landing on `UNKNOWN` regardless of export timing — silently breaking `OL01`'s premise rather than
  validating it. §5.2 now instead adopts option (b): `seller_customer_cross_state` is declared
  `DECISION_TIME` by explicit statement in this document, checked against the real `travel_month`
  precedent (`HANDOFF-059`), which turns out to use the identical shape (an explicit declared-lineage
  exception, not an organic classifier match) rather than assumed to be analogous. The atom's two
  *inputs* (`seller_state`, `customer_state`) remain fully subject to the real `classify_columns()`
  call, not exempted.
- **Why:** round 1 found the round-1 text silent on before/after CSV-export ordering, which could let
  the derived atom bypass the "every feature must be classifier-labeled" rule the document states as
  binding for everything else. This revision resolves the ambiguity by checking which resolution is
  actually mechanically accurate, per the review's own instruction, rather than picking the
  superficially "preferred" option without verification.
- **What did NOT change:** the atom's own definition (`seller_state != customer_state`), its
  construction from decision-time-only inputs, or its use in `OL01` — only the account of how it
  enters the classified feature set.

**Addressed, not required as a rewrite — point 3, Stage-1/Stage-2 execution ordering.**
- **What changed:** new §6.0 adds a binding execution-order requirement: §4.2's leakage audit must be
  run to completion and recorded in §12, per pattern per scale, before that pattern's own Stage 1
  oracle-detectability verdict is computed or inspected by anyone in the (single, uninterrupted)
  executing session.
- **Why:** round 1 confirmed the multiplicity-borrowing mechanism itself (§6.1 step 6) is
  mechanistically sound, matching `task-069`'s own precedent, but flagged that `task-069`'s precedent
  reused an already-frozen historical run, whereas this experiment's leakage audit, Stage 1, and Stage
  2 all run together in one session here — a real, previously-unstated path by which a Stage-1 result
  could retroactively influence which features "pass" the leakage audit. §6.0 closes that path
  explicitly rather than leaving it to session discipline alone.
- **What did NOT change:** §6.1's oracle-detectability method itself, step-for-step; §6.1 step 6's
  multiplicity-borrowing mechanism; §6.2/§6.3's discovery and validation protocols.

**Addressed, not required as a rewrite — point 5, well-known-dataset prior-knowledge risk.**
- **What changed:** new §7.1 states squarely that this document cannot rule out that the *choice* of
  which two outcomes and which four feature/outcome pairings were worth pre-registering — not just
  their thresholds — was shaped by generic prior familiarity with this specific, famous dataset's own
  well-known public findings, and that the document should not be read as implying hypothesis
  *selection* is as cleanly blind as threshold *mechanics* are.
- **Why:** round 1 judged this risk more serious than the round-1 §7 text credited, given the
  reviewer's own generic familiarity with widely-published Olist EDA notebooks. The round-1 text
  disclosed the risk but framed it primarily around threshold values; the review asked for a squarer
  acknowledgment that selection itself is not immune.
- **What did NOT change:** `OL01`–`OL04` are not discarded, reworded, or replaced — round 1
  independently confirmed they remain genuinely falsifiable and that their thresholds are cleanly
  data-relative, and this revision does not revisit either finding.

**Confirmed unchanged, per this task's own explicit instruction not to relitigate what round 1 already
confirmed sound:** all four hypotheses' own feature choices, rules, outcomes, hypothesized directions,
tie-break rule, and the explicit non-use of `price`/`freight_value`/`product_weight_g` (§5.3); the
matched-scale, development-only downsample design and its seed/row-count (§2.5); the direct-call
classification-path decision and the CSV-export fidelity requirement (§3, apart from §5.2's own
resolution above); the `TASK-008` foreknowledge handling (§1); every cited code-reuse
(`minimum_detectable_effect`, `benjamini_hochberg_adjusted`, `ValidationThresholds`,
`MATCH_RECALL_THRESHOLD`, `evaluated_hypotheses`); §9's interpretation branches, verbatim; §11's
scope exclusions. None of this is touched by this revision.
