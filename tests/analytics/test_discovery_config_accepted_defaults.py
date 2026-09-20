"""Bind `DiscoveryConfig`'s actual runtime defaults to a recorded "currently accepted defaults"
manifest (`TASK-077`, `ADR-070`).

Why this test exists: `TASK-064` (commit `a1be806`, 2026-08-22) introduced
`beam_rules_per_structure` with dataclass default `2` -- the exact value that same task's official
run went on to test and reject as an improvement. The task's `TASKS.md` closure prose then claimed
"not adopted as default", but no commit ever changed the field: `2` was `DiscoveryConfig`'s sole
default from the moment the field existed. That false claim was silently believed for eight days
and two further engine revisions (`TASK-068`) until `TASK-073` happened to `grep` the code
(`TASK-076`, `ADR-070`). `ADR-070` is the design authority for this test: a drift detector would not
have caught this specific failure (nothing ever changed -- the bug was a false claim made once, at
authorship time), so this test exists to run *at that same authorship time*, in CI, on every commit:
it fails immediately, and loudly, whenever `engine.py`'s real field defaults and this file's own
recorded manifest disagree, naming the diverged field so the disagreement cannot go unnoticed the
way `beam_rules_per_structure` did.

Scope, per `ADR-070`: `DiscoveryConfig` only. `ADR-070` explicitly declines to generalize this
pattern to `ValidationThresholds`, `GATE_SPECS`, or any other class on a sample size of one.
"""

from __future__ import annotations

import dataclasses

import pytest
from policy_analytics.discovery.engine import DiscoveryConfig

pytestmark = pytest.mark.analytics

# ACCEPTED_DEFAULTS -- the "currently accepted defaults" manifest `ADR-070` authorizes.
#
# One entry per `DiscoveryConfig` field (19 fields as of this writing -- `engine.py`, commit
# `dd81ea9`, `TASK-068`). Each value is commented with the task/ADR that last approved it, seeded
# by reading `engine.py`'s own field docstrings (each field narrates its own provenance) and
# cross-checked against `git blame`/`git log -p` on that file and the cited `TASKS.md`/
# `DECISIONS.md` entries.
#
# This dict may only be edited by a human/agent making a conscious statement that a new value is
# the newly accepted one -- never to silently make a failing test pass. See the failure message
# below (`_mismatch_message`) for the two legitimate ways to resolve a divergence.
ACCEPTED_DEFAULTS: dict[str, object] = {
    # The following 11 fields date to `engine.py`'s original commit (`317bde0`, 2026-08-13,
    # "first tasks"), `TASK-015` ("Discovery engine v0"). None carries a field-level docstring in
    # `engine.py` (confirmed via `git blame`), and none has been touched by any later commit --
    # `TASK-058`/`TASK-060`/`TASK-064`/`TASK-068` each added or changed a different field, never
    # one of these. Recorded as the original, never-revised `TASK-015` defaults.
    "seed": 1729,  # TASK-015 (commit 317bde0, 2026-08-13) -- original engine v0 default; unrevised.
    "min_support": 0.01,  # TASK-015 (commit 317bde0, 2026-08-13) -- original engine v0 default.
    "max_support": 0.40,  # TASK-015 (commit 317bde0, 2026-08-13) -- original engine v0 default.
    "min_n": 40,  # TASK-015 (commit 317bde0, 2026-08-13) -- original engine v0 default.
    "max_conditions": 3,  # TASK-015 (commit 317bde0, 2026-08-13) -- original engine v0 default.
    "beam_width": 80,  # TASK-015 (commit 317bde0, 2026-08-13) -- original engine v0 default.
    "top_k": 15,  # TASK-015 (commit 317bde0, 2026-08-13) -- original engine v0 default.
    "numeric_quantiles": (0.2, 0.4, 0.6, 0.8),  # TASK-015 (commit 317bde0, 2026-08-13) -- original.
    "max_categorical_levels": 12,  # TASK-015 (commit 317bde0, 2026-08-13) -- original engine v0.
    "max_candidate_jaccard": 0.85,  # TASK-015 (commit 317bde0, 2026-08-13) -- original engine v0.
    "max_candidates_per_atom": 5,  # TASK-015 (commit 317bde0, 2026-08-13) -- original engine v0.
    # `beam_rules_per_structure` -- the field this task exists because of. Introduced by `TASK-064`
    # (commit `a1be806`, 2026-08-22) at dataclass default `2`. `TASK-064`'s own official run
    # (`task-064-beam-20260822-001`) tested `2` against the pre-existing baseline (`0`, i.e. no
    # structural reserve) and rejected it as an improvement -- "No further tuning of
    # `beam_rules_per_structure` authorized" (`TASKS.md`, TASK-064 final statistical evaluation,
    # 2026-08-22). The closure prose also said "`discovery-engine-v0.5.0` ... is not adopted as
    # default", but that was never true of the code: `2` was the field's sole value from the moment
    # it existed, through `TASK-068`, and remains so. `TASK-064`'s closure-text correction
    # (`TASKS.md`, 2026-08-29, `TASK-076` part 1, `ADR-069` Branch 2) and `ADR-070` (this task's own
    # design authority) both record `2` -- not `0` -- as the currently accepted value: `ADR-070`
    # explicitly authorizes no change to this field and states the manifest it authorizes "will
    # record `2` as the currently-accepted value (matching the code ... ), with a comment citing
    # this ADR and TASK-064's corrected closure text -- not `0` or any other value."
    "beam_rules_per_structure": 2,  # TASK-064 (a1be806); corrected TASK-064 closure text + ADR-070.
    # Introduced alongside `beam_rules_per_structure` by the same `TASK-064` commit (`a1be806`),
    # implementing `ADR-046`'s expansion-beam design (`ADR-045` is the pre-code diagnosis that
    # motivated it, not the implementation decision itself).
    "max_expansion_beam_size": 512,  # TASK-064 (commit a1be806, 2026-08-22), ADR-046.
    # `TASK-058` (`HANDOFF-043` remediation part 2), `ADR-023` -- population-dampened beam-survival
    # score. Introduced at `0.5` (commit `1fc744b`, 2026-08-17) and never changed since.
    "population_score_exponent": 0.5,  # TASK-058 (commit 1fc744b, 2026-08-17), ADR-023.
    # `TASK-060` introduced this field at `1.0` (commit `d491642`, 2026-08-19, `ADR-035`); the
    # `v0.3.1` iteration lowered it to `0.5` (commit `2c6f6e0`, 2026-08-20, `ADR-037`), which is the
    # value the field carries today.
    "diversity_discount_weight": 0.5,  # TASK-060 iter. v0.3.1 (2c6f6e0, 2026-08-20), ADR-037.
    "min_diversity_relevance_ratio": 0.5,  # TASK-060 iter. v0.3.1 (2c6f6e0, 2026-08-20), ADR-037.
    # `TASK-060` iteration, `ADR-039` -- stability-credited effective score. Introduced at `0.5`
    # (commit `7405476`, 2026-08-20) and retained even though `ADR-039` found it empirically null on
    # the run it was tested against (a real, correctly-working capability, just insufficient alone).
    "stability_credit_weight": 0.5,  # TASK-060 iteration (commit 7405476, 2026-08-20), ADR-039.
    # `TASK-060` iteration, `ADR-040` -- floor reference point changed from the pool's maximum to
    # its own 75th percentile. Introduced at `0.75` (commit `24e7737`, 2026-08-20), unchanged since.
    "relevance_floor_percentile": 0.75,  # TASK-060 iteration (commit 24e7737, 2026-08-20), ADR-040.
    # `TASK-068`, `ADR-056`/`ADR-057` -- feature-identity diversity cap at final selection.
    # Introduced at `1.0` (commit `9a4eee1`, 2026-08-22), which never binds (equals `top_k` itself),
    # so `discovery-engine-v0.5.0` selection is reproduced exactly; unchanged since.
    "max_feature_identity_fraction": 1.0,  # TASK-068 (commit 9a4eee1, 2026-08-22), ADR-056/ADR-057.
}


def _mismatch_message(field: str, accepted: object, actual: object) -> str:
    return (
        f"DiscoveryConfig.{field}'s actual runtime default is {actual!r}, but "
        f"ACCEPTED_DEFAULTS[{field!r}] in "
        "tests/analytics/test_discovery_config_accepted_defaults.py records the currently "
        f"accepted value as {accepted!r}.\n"
        "\n"
        "This is a 'a default changed -- was that decision recorded?' check (TASK-077, ADR-070), "
        "not a generic test failure. A DiscoveryConfig default in engine.py no longer matches what "
        "was last consciously approved. Resolve this by doing exactly one of the following, "
        "whichever is actually correct -- do not silently pick one without checking:\n"
        f"  (a) If {actual!r} is a genuine, intended new default (a real decision was made to "
        f"change {field}): update ACCEPTED_DEFAULTS[{field!r}] to {actual!r} in this file, with a "
        "new, dated comment naming the task/ADR that approved the change.\n"
        f"  (b) If {actual!r} is unintentional drift (nobody meant to change {field}): fix "
        f"engine.py's DiscoveryConfig.{field} back to {accepted!r}.\n"
        "\n"
        "This exact failure mode -- a field's real default silently diverging from what a task/ADR "
        "closure claimed was approved -- is what happened to beam_rules_per_structure across "
        "TASK-064/TASK-068 and went undetected for eight days (see ADR-070). Do not close this out "
        "without confirming which of (a)/(b) is true against the actual task/ADR record."
    )


def test_accepted_defaults_manifest_covers_exactly_discovery_configs_fields() -> None:
    """Catches a field added to/removed from `DiscoveryConfig` without updating this manifest."""
    actual_field_names = {f.name for f in dataclasses.fields(DiscoveryConfig)}
    manifest_field_names = set(ACCEPTED_DEFAULTS)
    missing_from_manifest = actual_field_names - manifest_field_names
    extra_in_manifest = manifest_field_names - actual_field_names
    assert not missing_from_manifest and not extra_in_manifest, (
        "ACCEPTED_DEFAULTS in tests/analytics/test_discovery_config_accepted_defaults.py no longer "
        "has exactly one entry per DiscoveryConfig field.\n"
        f"Fields in DiscoveryConfig, missing from the manifest: {sorted(missing_from_manifest)}\n"
        f"Fields in the manifest, no longer on DiscoveryConfig: {sorted(extra_in_manifest)}\n"
        "A field was added to or removed from engine.py's DiscoveryConfig without a matching "
        "update to this manifest (TASK-077, ADR-070). Add/remove the corresponding "
        "ACCEPTED_DEFAULTS entry, with a dated comment naming the task/ADR that introduced or "
        "removed the field, before this test can pass."
    )


@pytest.mark.parametrize("field", sorted(ACCEPTED_DEFAULTS))
def test_discovery_config_field_default_matches_accepted_manifest(field: str) -> None:
    """Each DiscoveryConfig() field default must equal ACCEPTED_DEFAULTS' recorded value for it.

    Compared field by field (not a single `dataclasses.asdict(...) == ACCEPTED_DEFAULTS` blanket
    equality) so a mismatch fails on, and names, the one field that actually diverged.
    """
    config = DiscoveryConfig()
    actual = getattr(config, field)
    accepted = ACCEPTED_DEFAULTS[field]
    assert actual == accepted, _mismatch_message(field, accepted, actual)
