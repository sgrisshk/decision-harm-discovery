"""TASK-107 Phase 2b: the benchmark-v2 target designs (`TargetSpec` / `generate_v2` hook).

Every design is a *rule string* in the ground-truth grammar (`benchmark_v2_scoring.parse_rule`); its
predicate is derived from that string, so the declared rule and the generated membership cannot
disagree. No v1 pattern literal is used (ADR-107 D11); the trap literals of `T01`-`T05` appear only
in DECLARED_OVERLAP designs (ADR-107 D6). The designs and doses are pre-declared in
`docs/benchmark/task-107-evidence/rev4-preregistration.md` (committed before any calibration run);
this module must not be edited after that commit except by a new dated revision.

Design selection is justified from oracle-detectability and structural requirements only (spec
section 2 (i)-(iii)); no engine or discovery output on any v2 draw exists or was used.
"""

# pyright: reportPrivateUsage=false
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from policy_analytics import benchmark_v2_scoring as scoring
from policy_analytics.synthetic_benchmark_v2 import Covariates, TargetDose, TargetSpec

#: Named effect doses on v1's three levers (extra cost EUR, cancellation logit, support rate),
#: grouped in three pre-declared LADDERS (effect structures). `M` and `H` are the Phase 1 doses
#: (spec 4.1); the rest are new and pre-declared. A design's rung is chosen by the mechanical,
#: bounded procedure in `rev4-preregistration.md` (never after a calibration run).
DOSES: dict[str, TargetDose] = {
    # mixed lever profile (cost, cancellation and support all raised)
    "ML": TargetDose(200.0, 0.50, 0.30),
    "M": TargetDose(300.0, 0.75, 0.50),
    "H": TargetDose(410.0, 1.05, 0.75),  # = v1 P01's configured effect
    "XL": TargetDose(600.0, 1.05, 0.75),
    "XXL": TargetDose(800.0, 1.05, 0.75),
    # loss-only (cost overrun; no cancellation or support change)
    "LO1": TargetDose(150.0, 0.0, 0.0),
    "LO2": TargetDose(200.0, 0.0, 0.0),
    "LO3": TargetDose(300.0, 0.0, 0.0),
    "LO4": TargetDose(400.0, 0.0, 0.0),
    "LO5": TargetDose(500.0, 0.0, 0.0),
    "LO6": TargetDose(650.0, 0.0, 0.0),
    "LO7": TargetDose(800.0, 0.0, 0.0),
    # cancellation-led (small cost, large cancellation-logit shift)
    "CX1": TargetDose(100.0, 1.8, 0.20),
    "CX2": TargetDose(100.0, 2.4, 0.30),
    "CX3": TargetDose(100.0, 3.0, 0.40),
}
LADDERS: dict[str, tuple[str, ...]] = {
    "mixed": ("ML", "M", "H", "XL", "XXL"),
    "loss": ("LO1", "LO2", "LO3", "LO4", "LO5", "LO6", "LO7"),
    "cancel": ("CX1", "CX2", "CX3"),
}

DECLARED_CLASSES = ("core_candidate", "challenge_candidate", "declared_overlap")


@dataclass(frozen=True, slots=True)
class TargetDesign:
    target_id: str
    rule: str
    dose_name: str
    declared_class: str
    trap_literal: str | None = None  # `feature=value` of the trap literal, DECLARED_OVERLAP only

    @property
    def dose(self) -> TargetDose:
        return DOSES[self.dose_name]

    @property
    def ladder(self) -> str:
        return next(name for name, rungs in LADDERS.items() if self.dose_name in rungs)

    @property
    def conditions(self) -> tuple[scoring.CondSpec, ...]:
        return scoring.parse_rule(self.rule)


DESIGNS: tuple[TargetDesign, ...] = (
    TargetDesign(
        "C01", "destination=Lisbon AND acquisition_channel=partner", "LO6", "core_candidate"
    ),
    TargetDesign("C02", "destination=Rome AND customer_segment=corporate", "LO6", "core_candidate"),
    TargetDesign(
        "C03",
        "product_category=premium AND acquisition_channel=partner AND discount_rate>=0.08",
        "LO6",
        "challenge_candidate",
    ),
    TargetDesign(
        "C04",
        "supplier=Cedar AND customer_segment=leisure AND trip_duration_days>=8",
        "LO5",
        "core_candidate",
    ),
    TargetDesign("C05", "supplier=DeltaSun AND discount_rate>=0.12", "LO3", "challenge_candidate"),
    TargetDesign(
        "C06",
        "destination=Reykjavik AND customer_type=returning AND discount_rate>=0.05",
        "LO5",
        "challenge_candidate",
    ),
    TargetDesign(
        "C07",
        "supplier=BlueWing AND acquisition_channel=direct AND party_size>=3",
        "CX1",
        "core_candidate",
    ),
    TargetDesign("C08", "payment_method=wallet", "H", "core_candidate"),
    TargetDesign(
        "C09",
        "destination=Tokyo AND customer_segment=leisure AND product_category=standard",
        "LO6",
        "core_candidate",
    ),
    TargetDesign(
        "C10",
        "customer_type=new AND acquisition_channel=referral AND trip_duration_days>=6",
        "LO7",
        "core_candidate",
    ),
    TargetDesign("C11", "destination=Tokyo AND customer_segment=family", "H", "core_candidate"),
    TargetDesign(
        "C12",
        "acquisition_channel=direct AND product_category=premium AND customer_segment=leisure",
        "XL",
        "core_candidate",
    ),
    TargetDesign(
        "C13",
        "destination=Reykjavik AND product_category=standard AND payment_method=card",
        "LO6",
        "core_candidate",
    ),
    TargetDesign(
        "C14",
        "customer_segment=leisure AND supplier=BlueWing AND discount_rate>=0.08",
        "LO2",
        "core_candidate",
    ),
    TargetDesign(
        "C15",
        "customer_type=returning AND acquisition_channel=direct AND trip_duration_days>=6",
        "LO3",
        "core_candidate",
    ),
    TargetDesign(
        "H01",
        "supplier=BlueWing AND destination=Zanzibar AND customer_type=new",
        "LO6",
        "challenge_candidate",
    ),
    TargetDesign(
        "H02",
        "supplier=DeltaSun AND customer_segment=corporate AND product_category=standard",
        "H",
        "challenge_candidate",
    ),
    TargetDesign(
        "H03",
        "customer_type=returning AND payment_method=card AND trip_duration_days>=8",
        "LO3",
        "challenge_candidate",
    ),
    TargetDesign(
        "D01",
        "acquisition_channel=paid_search AND destination=Rome AND customer_type=returning",
        "LO7",
        "declared_overlap",
        "acquisition_channel=paid_search",
    ),
    TargetDesign(
        "D02",
        "payment_method=bank_transfer AND product_category=standard AND discount_rate>=0.08",
        "ML",
        "declared_overlap",
        "payment_method=bank_transfer",
    ),
)


def rule_predicate(rule: str) -> Any:
    conditions = scoring.parse_rule(rule)

    def predicate(cov: Covariates) -> bool:
        return all(scoring._row_matches(cov[c.feature], c) for c in conditions)

    return predicate


def target_specs(designs: tuple[TargetDesign, ...] | None = None) -> tuple[TargetSpec, ...]:
    chosen = DESIGNS if designs is None else designs
    return tuple(TargetSpec(d.target_id, d.rule, rule_predicate(d.rule), d.dose) for d in chosen)


def design_index() -> Mapping[str, TargetDesign]:
    return {d.target_id: d for d in DESIGNS}
