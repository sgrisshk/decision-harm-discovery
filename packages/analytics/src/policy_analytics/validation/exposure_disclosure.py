"""User-facing exposure disclosure text (`TASK-085` §5.3, implemented `TASK-086`).

What is shown to a user when attribution is not possible — i.e. every real candidate today, since
tier 3 (`O2`) is `TASK-085` §5.2's disclosed "always-empty slot" (see `economic_impact.py`'s
`build_attributable_impact_result`). Two pieces, both reusing already-computed quantities only —
no new computation happens in this module:

1. **The `G16` caveat**, when `k >= 2` and `G16` has run: `G16`'s own per-atom composition-safety
   classification (`composition_safety.py`, already computed for every `k >= 2` promoted candidate
   and surfaced today in `CandidateInterim.diagnostics["composition_safety_atoms"]`), surfaced
   verbatim — never folded into a numeric adjustment to the reported exposure figure, exactly
   analogous to how `G16`'s own cap already travels with the candidate's evidence level without
   being folded into any point estimate.
2. **The plain non-identifiability statement**, always present: the portion of the reported
   exposure specifically attributable to the discovered mechanism (as opposed to co-selected
   records) cannot currently be estimated from this data — not "is small," not "is being refined."
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: `TASK-085` §5.3's own wording, verbatim — a plain disclosure of non-identifiability, matching
#: this project's own established disclosure culture (`validation-contract.md` §11's "Known
#: limitations" precedent). Never conditioned on evidence level: it is true at every tier this
#: project's pipeline can currently reach (1-2), because tier 3 (`O2`) is unreachable today.
NON_IDENTIFIABILITY_STATEMENT = (
    "The portion of this exposure specifically attributable to the discovered mechanism, as "
    "opposed to co-selected records, cannot currently be estimated from this data."
)


@dataclass(frozen=True, slots=True)
class ExposureDisclosure:
    """§5.3's full disclosure package for a candidate's reported exposure (tiers 1-2)."""

    g16_caveat: str | None
    non_identifiability_statement: str


def g16_composition_caveat(composition_safety_atoms: list[dict[str, Any]] | None) -> str | None:
    """§5.3's `G16` caveat, built from `G16`'s own already-computed per-atom classifications.

    `composition_safety_atoms` is exactly `CandidateInterim.diagnostics["composition_safety_atoms"]`
    (or its persisted-JSON equivalent) — one dict per atom with a `"classification"` key holding
    `"confound_like"` or `"indeterminate"` (`CompositionAtomClassification`'s only two values;
    `composition_safety.py` §"no reachable third state"). Returns `None` when `G16` did not run for
    this candidate (`k == 1`, so the diagnostics list is empty) — never a fabricated caveat for a
    single-condition rule `G16` is vacuously satisfied for.
    """
    if not composition_safety_atoms:
        return None
    total = len(composition_safety_atoms)
    confound_like = sum(
        1 for atom in composition_safety_atoms if atom.get("classification") == "confound_like"
    )
    indeterminate = sum(
        1 for atom in composition_safety_atoms if atom.get("classification") == "indeterminate"
    )
    parts: list[str] = []
    if confound_like:
        parts.append(
            f"{confound_like} of {total} conditions in this rule show no evidence against a "
            "confounding explanation."
        )
    if indeterminate:
        parts.append(
            "This rule's own condition structure could not rule out confounding for "
            f"{indeterminate} of {total} conditions."
        )
    return " ".join(parts) if parts else None


def build_exposure_disclosure(
    composition_safety_atoms: list[dict[str, Any]] | None,
) -> ExposureDisclosure:
    """Assemble §5.3's full disclosure package. Pure function of already-computed diagnostics —
    no estimation, no gate evaluation, nothing new computed here.
    """
    return ExposureDisclosure(
        g16_caveat=g16_composition_caveat(composition_safety_atoms),
        non_identifiability_statement=NON_IDENTIFIABILITY_STATEMENT,
    )
