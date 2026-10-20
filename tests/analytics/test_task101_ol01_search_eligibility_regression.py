"""TASK-101/ADR-096: both-direction regression for the `_eligible()`/`max_support` search-
eligibility fix, on `OL01`'s own real construction.

`TASK-100` found `OL01` (`seller_customer_cross_state -> OUTCOME_LATE`, real Kaggle Olist data,
`TASK-099`'s frozen pre-registration) oracle-detectable at both tested scales but never found by
`discover_candidates()`: its raw rule has ~66% support on real data, above
`DiscoveryConfig.max_support=0.40`, so `_eligible()` excluded it at depth 1 regardless of the
effect's real strength or safety. `TASK-101`'s own binding mandate (`TASKS.md`) requires this
regression to be proven "on a real reproduction of `OL01`'s own construction (real Olist data,
matching `TASK-099`'s own pre-registered rule ... not a synthetic neutral-form test" -- this file
is that reproduction, reusing `scripts/task100_run_experiment.py`'s own already-reviewed join/
split/classification/outcome pipeline verbatim (imported, not re-derived) so the frame this test
runs `discover_candidates()` against is built by the identical, already-scrutinized code path
`TASK-100`'s own results (`docs/benchmark/task-100-sample-size-detectability-results.md`) used --
only the matched (4,999-row) development scale is used here, since `TASK-100` already established
both scales land on the identical verdict for `OL01` (oracle-detectable, never found, at either
scale) and the matched scale is far cheaper to rerun in a test suite.

A second, synthetic test of the general (non-`OL01`-specific) mechanism follows, additionally --
per `TASK-101`'s own "welcome but does not replace" allowance -- demonstrating the fix admits a
high-support rule specifically when its comparison group is adequate, and continues to exclude one
whose comparison group is not, on data with no relationship to Olist or any real domain.

Requires the real Kaggle "Brazilian E-Commerce Public Dataset by Olist" to already be present in
the local `kagglehub` cache (as `TASK-100`'s own run left it, and as this repository's other
Olist-dependent tooling expects -- no network fetch is attempted here). Skipped, not failed, when
that cache is absent, matching this project's own precedent for external-data-dependent checks.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import polars as pl
import pytest

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY / "packages/analytics/src"))
sys.path.insert(0, str(REPOSITORY / "packages/schemas/src"))

from policy_analytics.discovery.engine import (  # noqa: E402
    Condition,
    DiscoveryConfig,
    SplitMetric,
    _eligible,
    _metric,
    discover_candidates,
)

pytestmark = [pytest.mark.analytics, pytest.mark.slow]

TASK100_SCRIPT = REPOSITORY / "scripts" / "task100_run_experiment.py"
KAGGLEHUB_CACHE = Path.home() / ".cache/kagglehub/datasets/olistbr/brazilian-ecommerce/versions/2"

_REQUIRED_OLIST_CSVS = (
    "olist_orders_dataset.csv",
    "olist_order_items_dataset.csv",
    "olist_order_payments_dataset.csv",
    "olist_order_reviews_dataset.csv",
    "olist_customers_dataset.csv",
    "olist_products_dataset.csv",
    "product_category_name_translation.csv",
    "olist_sellers_dataset.csv",
)


def _olist_cache_available() -> bool:
    return KAGGLEHUB_CACHE.is_dir() and all(
        (KAGGLEHUB_CACHE / name).is_file() for name in _REQUIRED_OLIST_CSVS
    )


def _load_task100_module() -> ModuleType:
    """`scripts/` is not an importable package; load the real, committed `TASK-100` script the same
    way `tests/blind_agent/test_run_discovery_signed_config.py` already loads `scripts/
    run_discovery.py` -- by file path, not by re-deriving its logic here."""
    spec = importlib.util.spec_from_file_location("task100_run_experiment", TASK100_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: Verbatim reproduction of `_eligible()`'s body exactly as it stood before `TASK-101`/`ADR-096`
#: (every version of `packages/analytics/src/policy_analytics/discovery/engine.py` through
#: `discovery-engine-v0.6.1`, i.e. `config.min_support <= metric.support <= config.max_support` as
#: the sole support condition). Kept here as an explicit, dated copy -- not imported, since the
#: real `_eligible()` has since changed -- so this test can prove the *old* formula's real verdict
#: on real, freshly-computed Olist data even though that formula no longer exists in `engine.py`
#: itself. See `docs/analytics/task-101-max-support-search-eligibility-fix.md` and `ADR-096` for
#: the full citation trail.
def _pre_task101_eligible(metric: SplitMetric | None, config: DiscoveryConfig) -> bool:
    return bool(
        metric
        and metric.n_exposed >= config.min_n
        and config.min_support <= metric.support <= config.max_support
        and metric.harm_per_booking > 0
    )


def _build_ol01_matched_run_frame() -> tuple[pl.DataFrame, object, tuple[str, ...]]:
    """Real Olist data, matched (4,999-row development) scale, `OUTCOME_LATE` -- the identical
    frame `TASK-100`'s own Phase 5 (Stage 2) fed to `discover_candidates()` for this exact
    outcome/scale, built via that script's own real, already-reviewed functions."""
    task100 = _load_task100_module()
    frame = task100.phase1_join()
    frame, _split_info = task100.phase2_split(frame)
    matched = task100.build_matched_downsample(frame)
    classifications = task100.phase3_classify(frame)

    dev_matched_raw = matched.filter(pl.col("split_label") == "development")
    frame_matched_outcomes, _p25 = task100.add_outcomes(
        matched, development_only_for_p25=dev_matched_raw
    )
    dev_matched = frame_matched_outcomes.filter(pl.col("split_label") == "development")

    outcome = task100.outcome_definitions()["OUTCOME_LATE"]
    feature_cols = task100.feature_columns_for(classifications, "OUTCOME_LATE")
    eligible = dev_matched.filter(pl.col("OUTCOME_LATE_eligible"))
    # order_id is kept (not a search feature -- absent from feature_cols) purely so this test can
    # independently verify recall against OL01's own real affected-order set, the same way
    # scripts/task100_run_experiment.py's own match_candidates_to_pattern does.
    run_frame = eligible.select([*feature_cols, outcome.column, "split_label", "order_id"])
    return run_frame, outcome, feature_cols


@pytest.fixture(scope="module")
def ol01_matched_fixture() -> tuple[pl.DataFrame, object, tuple[str, ...]]:
    if not _olist_cache_available():
        pytest.skip(
            "real Olist dataset not found in the local kagglehub cache "
            f"({KAGGLEHUB_CACHE}); this regression requires the real data TASK-100 used, per "
            "TASK-101's own binding mandate -- not a synthetic stand-in."
        )
    return _build_ol01_matched_run_frame()


OL01_RULE: tuple[Condition, ...] = (Condition("seller_customer_cross_state", "eq", 1),)


def test_old_formula_genuinely_misses_ol01_real_rule(
    ol01_matched_fixture: tuple[pl.DataFrame, object, tuple[str, ...]],
) -> None:
    """Direction 1 (mandatory): reproduces `TASK-100`'s own finding directly, on freshly computed
    real Olist data -- the pre-`TASK-101` formula excludes `OL01`'s real rule purely because its
    real support exceeds `max_support`, not for any other reason."""
    run_frame, outcome, _feature_cols = ol01_matched_fixture
    config = DiscoveryConfig()
    metric = _metric(run_frame, OL01_RULE, outcome, "development")

    assert metric is not None
    # TASK-100's own real number was ~66% (matched scale); re-derived here independently.
    assert 0.60 <= metric.support <= 0.72, (
        f"OL01's real matched-scale support ({metric.support:.4f}) drifted far enough from "
        "TASK-100's own recorded ~66% that this is no longer the same reproduction -- investigate "
        "before trusting the rest of this test."
    )
    assert metric.support > config.max_support, (
        "OL01's real support must exceed max_support=0.40 for this regression to mean anything "
        f"(got support={metric.support:.4f})."
    )
    assert metric.harm_per_booking > 0  # a real, correctly-signed effect, not excluded on safety
    assert metric.n_exposed >= config.min_n  # not excluded by the (unrelated) exposed-side floor

    # The actual regression: the old formula says ineligible, purely on the support ceiling.
    assert _pre_task101_eligible(metric, config) is False


def test_new_mechanism_admits_ol01_real_rule_through_to_validation(
    ol01_matched_fixture: tuple[pl.DataFrame, object, tuple[str, ...]],
) -> None:
    """Direction 2 (mandatory): the real, current `_eligible()` now admits the identical rule --
    and `discover_candidates()`'s real, unmodified end-to-end search actually hands it onward as
    part of a final candidate (not merely eligible in isolation), i.e. admitted through to the
    point `run_validation` would receive it."""
    run_frame, outcome, feature_cols = ol01_matched_fixture
    config = DiscoveryConfig()
    metric = _metric(run_frame, OL01_RULE, outcome, "development")
    assert metric is not None

    # The comparison-group escape hatch this task adds is genuinely satisfied on real data, not
    # assumed: the comparison side is ~1,645 real rows at this scale, far above min_n=40.
    n_comparison = metric.n_population - metric.n_exposed
    assert n_comparison >= config.min_n

    assert _eligible(metric, config) is True

    # Full, unmodified real search: OL01's own atom must actually reach a final selected candidate,
    # not merely pass _eligible() in isolation.
    result = discover_candidates(run_frame.drop("order_id"), feature_cols, outcome, config)
    assert result["candidate_count"] > 0

    def _touches_ol01_atom(conditions: list[dict[str, object]]) -> bool:
        return any(
            c["feature"] == "seller_customer_cross_state" and c["operator"] == "ge"
            for c in conditions
        )

    matching_candidates = [c for c in result["candidates"] if _touches_ol01_atom(c["conditions"])]
    assert matching_candidates, (
        "no final candidate under the new mechanism uses OL01's own atom "
        "(seller_customer_cross_state) at all -- the fix did not actually reach "
        "discover_candidates' real output on this real data."
    )

    # Stronger, recall-based confirmation, matching TASK-100's own match_candidates_to_pattern
    # methodology exactly (>=50% of OL01's own real affected orders recovered by one candidate).
    pattern_exposed = frozenset(
        run_frame.filter(pl.col("seller_customer_cross_state") == 1)["order_id"].to_list()
    )
    assert pattern_exposed  # sanity: real, non-empty affected population

    def _candidate_exposed_ids(conditions: list[dict[str, object]]) -> frozenset[str]:
        expr: pl.Expr | None = None
        for cond in conditions:
            feature, op, value = cond["feature"], cond["operator"], cond["value"]
            col = pl.col(str(feature))
            atom_expr = (
                col == value
                if op == "eq"
                else (col.cast(pl.Float64) >= float(value))  # type: ignore[arg-type]
                if op == "ge"
                else (col.cast(pl.Float64) < float(value))  # type: ignore[arg-type]
            )
            expr = atom_expr if expr is None else (expr & atom_expr)
        assert expr is not None
        mask = run_frame.select(expr.alias("_m"))["_m"]
        return frozenset(run_frame.filter(mask)["order_id"].to_list())

    best_recall = max(
        len(_candidate_exposed_ids(c["conditions"]) & pattern_exposed) / len(pattern_exposed)
        for c in result["candidates"]
    )
    assert best_recall >= 0.5, (
        f"best real-candidate recall against OL01's own affected orders is only {best_recall:.3f}; "
        "TASK-100's own MATCH_RECALL_THRESHOLD is 0.5."
    )


# --------------------------------------------------------------------------------------------
# Additional (not a substitute for the above): synthetic, domain-agnostic mechanism test.
# --------------------------------------------------------------------------------------------


def _synthetic_frame_with_two_high_support_rules() -> pl.DataFrame:
    """No relationship to Olist, OL01, or any real domain -- purely to isolate the general
    "comparison group adequate vs. not" behavior the fix actually implements, independent of any
    one rule's specific numbers.

    `feature_safe` is a 70%-support flag with a real, correctly-signed effect whose comparison
    group is a comfortable 90 rows (>= min_n=40 used below): should become eligible now.
    `feature_thin` is a 97%-support flag with an equally real, correctly-signed effect whose
    comparison group is only 9 rows (< min_n=40): must remain excluded -- the fix is not "raise
    max_support", it is "admit only where the comparison side is still reliable".
    """
    rows = []
    for split in ("development", "validation", "future_holdout"):
        for index in range(300):
            feature_safe = index < 210  # 70% support, 90-row comparison group
            feature_thin = index < 291  # 97% support, 9-row comparison group
            outcome = 10.0
            if feature_safe:
                outcome += 5.0
            if feature_thin:
                outcome += 5.0
            rows.append((feature_safe, feature_thin, outcome, split))
    return pl.DataFrame(
        rows,
        schema=["feature_safe", "feature_thin", "OUTCOME_HARM", "split_label"],
        orient="row",
    )


def test_general_mechanism_admits_only_the_adequately_supported_comparison_group() -> None:
    """The synthetic, non-OL01 complement to the two tests above: proves the fix is a real,
    generic mechanism (comparison-group adequacy), not a number reverse-engineered from OL01's own
    66%. `feature_safe` (70% support, 90-row comparison) becomes eligible; `feature_thin` (97%
    support, 9-row comparison) stays excluded even after the fix, on the identical config."""
    from policy_analytics.outcomes.contract import MissingDataPolicy, OutcomeDefinition, OutcomeRole

    frame = _synthetic_frame_with_two_high_support_rules()
    outcome = OutcomeDefinition(
        outcome_id="OUTCOME_HARM",
        role=OutcomeRole.PRIMARY,
        column="OUTCOME_HARM",
        unit="eur",
        higher_is_worse=True,
        missing_data_policy=MissingDataPolicy.COMPLETE,
        description="synthetic",
        valid_range=(0.0, 100.0),
        aggregation_rule="mean",
        harm_direction_phrase="harm increases",
    )
    config = DiscoveryConfig(min_n=40)

    safe_metric = _metric(frame, (Condition("feature_safe", "eq", True),), outcome, "development")
    thin_metric = _metric(frame, (Condition("feature_thin", "eq", True),), outcome, "development")
    assert safe_metric is not None and thin_metric is not None

    assert safe_metric.support > config.max_support  # 0.70 > 0.40
    assert thin_metric.support > config.max_support  # 0.97 > 0.40
    assert (safe_metric.n_population - safe_metric.n_exposed) >= config.min_n  # 90 >= 40
    assert (thin_metric.n_population - thin_metric.n_exposed) < config.min_n  # 9 < 40

    # Old formula: both excluded, for the identical reason (support ceiling alone).
    assert _pre_task101_eligible(safe_metric, config) is False
    assert _pre_task101_eligible(thin_metric, config) is False

    # New mechanism: admits exactly the one whose comparison group is adequate.
    assert _eligible(safe_metric, config) is True
    assert _eligible(thin_metric, config) is False
