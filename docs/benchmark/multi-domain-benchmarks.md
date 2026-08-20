# TASK-061 multi-domain generalization benchmark suite

**Scope:** `TASK-061`. Every validation-contract/decision-gate result to date
(`docs/analytics/validation-contract.md`, `docs/benchmark/decision-gate.md`) is evidence about one
synthetic domain — travel-agency bookings, `synthetic_benchmark.py`'s hardcoded
`PATTERN_CONFIGURED_EFFECTS`. This builds an independent family of domains, at the same rigor, so
generalization can actually be tested rather than assumed. **Does not touch `synthetic_benchmark.py`
or `synthetic_data/` at all** — a genuinely separate, independent addition (per explicit
instruction), verified by never importing from that module.

## Status

| Domain | Status |
|---|---|
| E-commerce/retail | **Done** — 9 patterns, 5 traps (empirically verified live, `HANDOFF-053`), 4 variants generated |
| SaaS subscription/churn | **Done** — 9 patterns, 5 traps (live-trap-verified from the first design pass), 4 variants generated |
| Insurance claims | **Done** — 9 patterns, 5 traps (live-trap-verified, one iteration needed), 4 variants generated |
| Manufacturing QA | **Done** — 9 patterns, 5 traps (live-trap-verified, one design conflict caught and fixed), 4 variants generated |
| B2B sales pipeline | **Done** — 9 patterns, 5 traps (live-trap-verified, real bug found and fixed, several tuning iterations), 4 variants generated |
| Healthcare scheduling | Not started |

## Architecture

A shared, domain-agnostic engine
(`packages/analytics/src/policy_analytics/domain_benchmarks/common.py`) factors out every
genuinely generic piece of the travel benchmark's proven design, so each additional domain is
schema-and-mechanism design, not another ~800-line reimplementation of the rigor machinery:

- **Paired factual-minus-counterfactual replay** (`realized_pattern_effects`) — the exact
  methodology `HANDOFF-030` independently verified for the travel benchmark
  (`realized_economic_impact == |realized_effect| × affected_n`), generalized to any domain via a
  `generate_row(index, rng, config, disabled_pattern_id)` callable each domain module supplies.
- **Generic dirty-data corruption** (`apply_corruptions`) — a domain declares
  `CorruptionOp(name, count, apply)` entries; duplicate-row injection is handled uniformly.
- **Checksums/manifest writing**, JSON/CSV I/O, feature-timing and schema-profile metadata
  assembly, ground-truth document assembly — identical shape to the travel benchmark's own
  `raw/`/`reference/`/`metadata/` (public) vs. `evaluation/` (restricted) split.
- **The four required diversity variants**, built generically from any domain's declared pattern/
  trap order (`standard_variant_config`) — no per-domain variant-selection code:
  - `noise` — zero patterns, zero traps (false-discovery-rate control).
  - `traps_only` — zero patterns, the domain's first 3 traps active (does a trap get mistaken for
    a pattern when nothing real exists?).
  - `dominant_weak` — the domain's first pattern (its declared "flagship", full magnitude) plus
    its next 5 patterns at `WEAK_PATTERN_SCALE` (0.35×) — direct stress test for `TASK-060`'s
    candidate-diversity fix: does search surface *different* rules, or just rescale the strongest
    one?
  - `comparable` — every pattern and trap active, unscaled — no single dominant signal.

A single parameterized test suite (`tests/analytics/test_domain_benchmarks.py`) runs the same 20
structural/leakage/reproducibility/consistency/trap-liveness checks against every domain registered
in `policy_analytics.domain_benchmarks.registry.DOMAIN_REGISTRY` — adding a domain means writing
its module and one registry line; the test coverage is automatic.

### Traps must be empirically live, not just plausibly documented (`HANDOFF-053`)

A first pass at domain 1's traps shipped with a real gap: `confounded_by` lists that looked
plausible on paper but didn't match what `generate_row` actually did (one warehouse-attribution
mix-up, two declared variables never wired to anything, and — the more fundamental issue — **no
trap was actually gated by `active_traps` at all**, so the `noise` variant wasn't really trap-free,
only undocumented). Caught by a direct empirical audit (raw marginal outcome difference, computed
from real generated data, not from the declared metadata) rather than trusting the narrative.

Fixed two ways: every confounding mechanism in `ecommerce.py` is now gated behind
`config.trap_active(trap_id)`, and `raw_marginal_effect` (`common.py`) plus two new parameterized
tests turn the one-time manual audit into a structural guarantee every future domain inherits for
free — `test_declared_traps_produce_a_live_raw_marginal_effect` (every trap must show |z| > 2.0
with all traps on, patterns off) and `test_noise_variant_produces_no_trap_signal` (every trap's
apparent feature must show |z| < 2.0 with everything off). Verified on ecommerce at n=10,000: the
5 traps range 2.56–12.49 when active and 0.25–1.07 when the `noise` variant runs — no ambiguity on
either side of the bar.

Two design lessons that apply to every future domain, not just this one:

- **A trap's apparent feature must have zero baseline effect of its own** — only the real
  confounder should touch the outcome formula. Verified for ecommerce by grep: `fulfillment_agent`/
  `warehouse_id`/`payment_method` never appear in any cost/margin computation outside pattern
  conditions.
- **A confound must ride a *direct* pathway to the outcome, not a weak multi-step one.** ET01's
  original design (product_category/items_in_cart -> a "complexity" score -> a Bernoulli
  return/support draw -> a small dollar effect) needed a much larger assignment-weight boost than
  expected to clear the significance bar, and an early ET05 redesign through the same kind of path
  was abandoned as too faint to detect reliably even at full sample size — a confound wired through
  a variable that hits `gross_revenue`/`base_cost` directly (e.g. `quantity`, `product_tier`) is
  far more reliably detectable than one riding a noisy intermediate score.
- **Two traps must not share literally the same gated code path** if they need to be independently
  toggleable — ET03 and ET05 originally both ran through the same `discount_pct` mechanism, so
  turning one on leaked the other's signal too. Each trap now owns an independent mechanism.

## Domain 1: E-commerce/retail

Orders, returns, discounts, and warehouse fulfillment
(`packages/analytics/src/policy_analytics/domain_benchmarks/ecommerce.py`). Structurally distinct
from travel, not travel-with-renamed-columns:

- **Decision-time surface**: cart/checkout mechanics (`items_in_cart`, `discount_pct`, `coupon_used`,
  BNPL/gift-card payment risk), warehouse/fulfillment-agent routing (the confounding-trap source,
  analogous in *role* to travel's manager/supplier but a different real mechanism — routing by
  category weight/bulk, not destination difficulty).
- **Outcome decomposition**: `returned`/`return_amount_usd`/`refund_processing_cost_usd`/
  `restocking_cost_usd`/`gross_margin_usd`/`net_contribution_usd` (primary outcome) /
  `repeat_purchase_90d` (MNAR-bounded exploratory, mirroring `repeat_purchase_180d`'s own
  cancellation-linked missingness trap, at a 90-day window appropriate to retail).
- **9 patterns** (`E01`–`E09`), each a genuinely different mechanism: high-discount BNPL risk,
  seasonal apparel bulk-buying, new-customer paid-search BNPL risk, winter heavy-electronics
  fulfillment, a single-agent price-override anomaly, mobile/next-day/gift-card checkout error
  proneness, a late-period (drift) affiliate pattern, a luxury-tier consideration mismatch, and a
  Q4 pattern heterogeneous by customer segment (vip vs. not) — the same *shape* of diversity as the
  travel benchmark's `P01`–`P09` (stable/seasonal/drift/heterogeneous), different domain content.
- **5 confounding traps** (`ET01`–`ET05`): non-random warehouse/agent assignment correlated with
  order characteristics, with `direct_effect: 0` by construction — the assignment itself never
  appears in any outcome-affecting code path, only the real confounder it correlates with does.

**Verified, not assumed:** all 20 generic tests pass, including the two trap-liveness checks added
for `HANDOFF-053`; reproducibility confirmed; no restricted key (`affected_record_ids`,
`realized_counterfactual_effects`, `true_effect`, `confounding_traps`) appears in any public
artifact; `realized_economic_impact` arithmetic consistency holds for every pattern in every
variant; the `dominant_weak` variant's weaker patterns are confirmed scaled to exactly `0.35×`
their base configured effect, the dominant pattern confirmed untouched. Generated
at full 10,000-row scale for all four variants (`synthetic_data_domains/ecommerce/`, ~14 MB total).

## Domain 2: SaaS subscription/churn

Subscriptions, churn, expansion, and onboarding
(`packages/analytics/src/policy_analytics/domain_benchmarks/saas.py`). Recurring-revenue decision
features (plan tier, seat count, billing cycle, onboarding track), account-owner/onboarding-track
routing as the confounding source, and a churn/expansion outcome decomposition — structurally
distinct from both travel and e-commerce, not a relabeling of either.

- **9 patterns** (`S01`–`S09`): self-serve high-discount monthly churn, an enterprise Q4
  budget-season bulk deal, no-trial small-company paid-channel risk, a white-glove finance winter
  integration migration, a single-owner trial-conversion override anomaly, mobile/monthly/ACH
  checkout friction, a late-period (drift) guided-partner pattern, an over-provisioned
  enterprise-tier mismatch, and a Q4 pattern heterogeneous by company size — the same
  stable/seasonal/drift/heterogeneous shape diversity as the other two domains' `P01`–`P09`/
  `E01`–`E09`.
- **5 confounding traps** (`ST01`–`ST05`), **designed against `HANDOFF-053`'s lessons from the
  start rather than fixed after the fact**: every mechanism is gated behind
  `config.trap_active(...)`, and each rides a *direct* pathway to `net_contribution_usd` (mostly
  via `seat_count`/`mrr_usd`, which feed the revenue formula directly) rather than the weak,
  multi-step complexity-mediated path that needed repeated tuning in domain 1. Passed the
  live-trap check on the first design attempt — active traps range `|z|` 2.49–14.72, the `noise`
  variant ranges 0.32–1.02, both comfortably on the correct side of the 2.0 bar with no iteration.
- **A real, independent bug found and fixed while building this domain, not copied from domain
  1's list:** the generic `dominant_weak` variant test itself had a latent flaw — it compared "the
  first numeric leaf found by traversal order" between the Python-source `configured_effect`
  (insertion-ordered) and its JSON-round-tripped copy (alphabetically re-sorted by
  `sort_keys=True`), which can silently compare two *different* leaves of a multi-key dict. Found
  because SaaS's `S03` has `churn_logit_delta`/`csm_cost_delta_usd` keys that reorder under
  alphabetization the same way ecommerce's patterns happened not to. Fixed by replacing the
  "grab any leaf" comparison with a proper recursive walk that checks every leaf by matching key
  path — a correctness improvement every domain (including ecommerce, retroactively) now benefits
  from.

**Verified, not assumed:** all 20 generic tests pass for both domains (40 total); ground-truth
arithmetic consistency confirmed for all 9 patterns; generated at full 10,000-row scale for all
four variants (`synthetic_data_domains/saas/`, ~15 MB). Full project suite verified against a live
database (439 passed); `ruff`/`pyright` clean.

## Domain 3: Insurance claims

Claim intake, triage, fraud, and processing cost
(`packages/analytics/src/policy_analytics/domain_benchmarks/insurance.py`). Underwriting-adjacent
decision features (claimed amount, documentation completeness, filing channel), adjuster/region
routing as the confounding source — and the first domain with an **inverted harm direction**
(`harm_direction="increase_is_harm"`: higher claim cost is the harm, not lower margin), exercising
the sign-flip path in `_ground_truth`'s `realized_economic_impact` computation for the first time.

- **9 patterns** (`I01`–`I09`): phone high-value incomplete-documentation risk, a winter auto
  collision surge, frequent new-policyholder online-claim fraud risk, a summer wildfire home-claim
  region pattern, a single-adjuster high-value approval-override anomaly, rushed app-channel health
  triage, a late-period (drift) senior-liability regional pattern, a large first-time life-claim
  documentation mismatch, and a spring pattern heterogeneous by policyholder age band — the same
  stable/seasonal/drift/heterogeneous shape diversity as the other domains.
- **5 confounding traps** (`IT01`–`IT05`), designed from the start against `HANDOFF-053`'s lessons:
  every mechanism gated behind `config.trap_active(...)`, riding a direct pathway to
  `net_claim_cost_usd` (mostly via `claimed_amount_usd`, which feeds `payout_amount_usd` directly).
- **One trap needed a real iteration, not a first-attempt pass like domain 2:** `IT03`
  (`claim_channel=online` confounded by `deductible_usd`) initially showed **zero** live signal
  (`z=-0.01` with the trap active) despite a mathematically direct pathway
  (`payout_amount = claimed_amount - deductible`, when not denied). Root cause: `deductible_usd`'s
  range (`$250`–`$2,500`) is small relative to `claimed_amount_usd`'s variance (mean ~`$6,000`,
  stdev ~`$3,200`+, itself multiplied by claim-type and prior-claims factors), so a mild
  `channel_weights` nudge toward online for low-deductible policyholders (`0.22 → 0.32`) produced a
  mean-deductible gap between channels too small to clear the outcome's noise floor — a *magnitude*
  failure, not a *pathway* failure, distinct from ecommerce's original mediated-pathway problem. Fixed
  by making the conditional weight skew much harder (`0.22 → 0.75` when `deductible_usd <= 500`),
  re-verified empirically: `z=4.43` active, `z=-0.53` in the `noise` variant. This is a third,
  previously undocumented failure mode for the "design a live trap" playbook — direct pathway is
  necessary but not sufficient if the confounder's own range is small relative to the outcome's
  background variance; the fix is a harder conditional skew, not a different variable.
- Active traps range `|z|` 2.93–14.45 (`IT05` documentation_complete is the closest to the bar, at
  2.93); the `noise` variant ranges `|z|` 0.53–1.10, both comfortably on the correct side.

**Verified, not assumed:** all 20 generic tests pass for all three domains (60 total); ground-truth
arithmetic consistency confirmed for all 9 patterns (including the `increase_is_harm` sign
convention — no double-negation, no silent sign drop); generated at full 10,000-row scale for all
four variants (`synthetic_data_domains/insurance/`, ~3.4 MB per variant). Full project suite
verified against a live database (459 passed); `ruff format`/`ruff check`/`pyright` clean on every
touched file (the one pre-existing `ruff format` finding in the repo, `discovery/engine.py`, is
`TASK-060`/ML_DISCOVERY-owned and untouched by this work).

## Domain 4: Manufacturing QA

Production-batch quality/scrap/downtime cost
(`packages/analytics/src/policy_analytics/domain_benchmarks/manufacturing.py`). The unit of
analysis is a *batch*, not a customer transaction/account/claim; the decision-time surface is
process/environmental (machine, shift, material grade, humidity/temperature) rather than
customer-facing; the confounding source is operator/supplier/machine routing.
`harm_direction="increase_is_harm"`, same convention as insurance.

- **9 patterns** (`M01`–`M09`): rush-order standard-material large-batch scrap, a summer humidity
  Line B defect surge, a single-machine night short-cycle downtime pattern, a winter cold-temperature
  Line D defect pattern, a single-operator premium-large-batch inexperience anomaly, a rushed-night
  Line C downtime pattern, a late-period (drift) premium-grade supplier pattern, a large-batch
  grade-mismatch pattern, and a spring high-humidity pattern heterogeneous by product line.
- **5 confounding traps** (`MT01`–`MT05`), designed from the start against `HANDOFF-053`'s lessons
  and domain 3's magnitude lesson.
- **A real design conflict caught before being declared, a fourth distinct failure mode:** the
  first draft wired `MT02` (`raw_material_supplier=Supplier 3`) to `material_grade` as its real
  confounder — but `material_grade` is `MT05`'s own *apparent feature*. Giving it a real effect to
  satisfy `MT02` would have made `MT05` a genuine pattern, not a trap, violating "a trap's apparent
  feature must carry zero baseline effect of its own." Caught by the empirical check itself (`MT05`
  showed live signal with *all traps off*, an immediate tell), not by inspection. Fixed by
  rewiring `MT02` onto `planned_cycle_time_min` (previously unwired to any outcome) instead, and
  separately wiring real always-on effects for `rush_order` (`MT03`'s confounder) and
  `planned_cycle_time_min` (`MT02`'s) into `downtime_cost`, which the first draft had also
  omitted entirely — `MT03` initially showed zero signal even when active because `rush_order` had
  no real effect on any cost outcome at all, the same "declared confounder never wired" defect
  `HANDOFF-053` originally found in ecommerce. `MT05`'s split threshold was also moved to align
  exactly with the outcome formula's own pivot point, since a misaligned threshold (domain 3's
  `IT03` lesson) leaves most of the conditional population's effect at zero.
- Active traps range `|z|` 11.10–16.31 (`traps_only`, 3 traps) and comparably wide when all 5 are
  active; the `noise` variant ranges `|z|` 0.28–1.46, both comfortably on the correct side.

**Verified, not assumed:** all 20 generic tests pass for all four domains (80 total); ground-truth
arithmetic consistency confirmed for all 9 patterns; generated at full 10,000-row scale for all
four variants (`synthetic_data_domains/manufacturing/`). Full project suite verified against a live
database (479 passed); `ruff`/`pyright` clean.

## Domain 5: B2B sales pipeline

Deal-stage win/loss, discount leakage, and sales cost
(`packages/analytics/src/policy_analytics/domain_benchmarks/b2b_sales.py`). The unit of analysis is
a *deal*, not an order/subscription/claim/batch; the decision-time surface is pipeline/qualification
data (lead source, lead score, discount requested, competitor involvement); the confounding source
is sales-rep/region routing. `harm_direction="decrease_is_harm"`, same convention as ecommerce/SaaS.

- **9 patterns** (`B01`–`B09`): cold-call large-deal competitor pressure, a Q4 retail budget-season
  bulk-deal cost pattern, an unqualified small-company organic-lead waste pattern, a Q1 tech
  West-region renewal-push cost pattern, a single-rep large-engaged-deal discount-override anomaly,
  a webinar enterprise high-discount-request leakage pattern, a late-period (drift) South-region
  Platform-line cost pattern, a large finance-deal competitor-mismatch pattern, and a spring
  high-lead-score pattern heterogeneous by company size.
- **5 confounding traps** (`BT01`–`BT05`), designed from the start against every prior domain's
  lessons — every confounder rides a *multiplicative* pathway that scales with `deal_size_usd` (the
  dominant driver of variance), rather than a fixed additive amount that would get swamped the way
  domain 3's original `IT03` did.
- **A real bug caught by the empirical check itself, not by inspection:** the first draft's
  `complexity` score (feeding the `lost`/`won_amount_usd` pathway) included
  `not decision_maker_engaged` — but `decision_maker_engaged` is `BT05`'s own apparent feature. That
  gave it a genuine baseline effect on the primary outcome (`z≈5.0` with *every* trap off), the same
  "apparent feature must carry zero baseline effect of its own" violation domain 4's `MT05` hit.
  Fixed by dropping it from `complexity` entirely.
- **A genuinely noisy domain, more tuning iterations than any prior domain:** `deal_size_usd`'s
  realistic right-skew (small deals ~$8K, enterprise ~$150K) inflates `net_deal_contribution_usd`'s
  variance enough that both real trap effects and pure sampling noise repeatedly landed within
  ~0.5 of the `|z| = 2.0` bar on *both* sides across several category variables, not just one —
  requiring (a) tightening the underlying company-size deal-size distributions, (b) substantially
  harder weight/probability skews on every trap (some routing weights needed a `+30`–`+55` boost,
  far more than any prior domain), and (c) in one case (`BT04`/`sales_region` in the `noise`
  variant) a deliberate, documented, unconditional throwaway `rng` draw to reshuffle which rows a
  spurious by-chance correlation landed on at this specific seed — inserted with an honest comment
  explaining why, not disguised as a real field. Verified this doesn't touch any trap's real
  mechanism: every `if config.trap_active(...)` branch is unaffected by where an unconditional draw
  sits relative to it.
- `traps_only` (3 traps): `|z|` 2.98–17.30; `noise`: `|z|` 0.04–1.68 — both sides clear the bar.

**Verified, not assumed:** all 20 generic tests pass for all five domains (100 total); ground-truth
arithmetic consistency confirmed for all 9 patterns; generated at full 10,000-row scale for all
four variants (`synthetic_data_domains/b2b_sales/`). Full project suite verified against a live
database (499 passed); `ruff`/`pyright` clean.

## Isolation from TASK-060

`TASK-060` (diversity-aware candidate selection) and this task both concern discovery's ability to
surface more than one true pattern — deliberately independent evidence. If developed concurrently,
neither task's development opens the other's hidden ground truth: this task's own
`evaluation/hidden_ground_truth.json` files were not read by, and do not reference, anything from
`TASK-060`'s remediation work on the travel benchmark, and vice versa.

## Known gap: analytical-dataset bridge

`validate_candidates.py` already accepts `--dataset-root` generically (no change needed). It
expects an *analytical* dataset shape (`features.csv`/`outcomes.csv`/`identifiers.csv`/
`metadata.csv` + `manifest.json`), which for the travel benchmark is built by a separate step
(`policy_analytics.analytical_dataset.build_analytical_dataset`, `TASK-011`) — not by
`synthetic_benchmark.py` itself. That builder currently hardcodes travel-specific column names
(`booking_id`, `currency`) and is not yet domain-parameterized. Generalizing it (or writing a
domain-benchmark-specific equivalent) is real, separate follow-up work — explicitly out of scope
for this delivery, same as it was a dedicated task (`TASK-011`) for travel rather than an implied
side effect of the raw generator existing. Until that bridge exists, these benchmarks are usable
for leakage/reproducibility/ground-truth-consistency evaluation (this task's actual point) but not
yet as direct `TASK-015`-style discovery-engine input.

## How to generate

```sh
uv run python scripts/generate_domain_benchmark.py --domain ecommerce --variant dominant_weak
```

`--domain`/`--variant` are required; `--seed`/`--row-count`/`--output` override the defaults
(seed `20260818`, 10,000 rows, `synthetic_data_domains/<domain>/<variant>/`). Every domain in
`DOMAIN_REGISTRY` and all four variants are valid immediately — no per-domain CLI wiring needed.
