# Discovery Engine v0 — Technical Design

**Owner:** ML Discovery  
**Task:** TASK-015 design  
**Status:** Design only; this document does not authorize a discovery run  
**Evidence boundary:** Candidate generation, not causal or statistical validation

## 1. Purpose and boundaries

Discovery Engine v0 searches a leakage-safe analytical dataset for interpretable candidate
subgroups associated with a Statistics-defined harmful outcome direction. It produces 10–20
immutable candidate patterns for independent Statistics validation.

The engine must not:

- select, redefine, combine, or reweight the primary outcome;
- read hidden ground truth, generator code, evaluation artifacts, or private benchmark metadata;
- use identifiers, post-decision fields, outcomes, metadata, or unknown-timing fields as rule
  conditions;
- claim causal validity, assign an evidence grade, or propose deployment;
- edit a condition after validation results are observed. A changed condition is a new hypothesis
  in a new run family.

All calculations are deterministic executable code. A generative model may later explain a persisted rule but
cannot generate thresholds, effects, support, exposure, or rank scores.

## 2. Typed candidate representation

The proposed domain types are independent of Polars and model libraries. Adapters translate them
to dataframe expressions.

```python
from dataclasses import dataclass
from enum import StrEnum

Scalar = str | int | float | bool

class Operator(StrEnum):
    EQ = "eq"
    LT = "lt"
    LE = "le"
    GT = "gt"
    GE = "ge"
    IN = "in"

@dataclass(frozen=True, slots=True)
class AtomicCondition:
    feature: str
    operator: Operator
    value: Scalar | tuple[Scalar, ...]
    feature_dtype: str
    timing_classification: str  # must equal DECISION_TIME

@dataclass(frozen=True, slots=True)
class CandidatePattern:
    candidate_id: str
    conditions: tuple[AtomicCondition, ...]  # logical AND, canonical order
    source_method: str
    source_model_id: str | None
    fit_split: str
    discovery_family_id: str
```

Rules are conjunctions only in v0. Disjunctions and negated compound expressions are excluded
because they reduce auditability and make overlap/deduplication ambiguous. `IN` is permitted only
for a small explicit category set and is normalized to a sorted tuple.

Canonical identity is the SHA-256 of canonical JSON containing dataset identity, outcome-contract
identity, fit split, and sorted normalized conditions. Display text is derived from the structured
representation and is never the source of truth.

## 3. Support and complexity rules

Defaults are typed configuration, not scattered constants:

```python
@dataclass(frozen=True, slots=True)
class DiscoveryConfig:
    seed: int = 1729
    min_support_fraction: float = 0.01
    min_support_count: int = 50
    max_support_fraction: float = 0.40
    max_interaction_depth: int = 3
    requested_candidates: int = 15
    max_candidates: int = 20
    tree_max_depth: int = 3
    tree_min_leaf_count: int = 50
    boosting_max_depth: int = 3
    boosting_rounds: int = 200
    rule_beam_width: int = 100
    max_pairwise_jaccard: float = 0.85
```

A rule is eligible only when:

```text
exposed_n >= max(min_support_count, ceil(min_support_fraction * eligible_fit_n))
and exposed_n <= floor(max_support_fraction * eligible_fit_n)
and comparison_n satisfies the same absolute minimum count
```

The absolute floor prevents a large dataset from legitimizing tiny unstable segments; the
fractional floor prevents a small absolute group from being overrepresented in a very large
population. The maximum support rejects broad near-baselines masquerading as subgroups. Empty,
all-row, single-record, and identifier-equivalent rules are always rejected.

Maximum interaction depth is three atomic conditions. This supports actionable forms such as
`discount > X AND lead_time < Y AND supplier = Z` while keeping rules reviewable and limiting the
hypothesis family. A future depth increase requires a versioned config and must not be chosen after
seeing validation outcomes.

## 4. Baseline candidate generators

All generators receive the same fit partition, allowlisted feature schema, fixed outcome-contract
reference, eligible-cohort mask, and seed. They emit structured rules only; a shared evaluator
computes support and raw descriptive metrics.

### 4.1 Shallow decision trees

- Fit a deterministic regression or classification tree according to the supplied outcome type.
- Limit depth to three and enforce the shared minimum leaf size.
- Extract every harmful leaf path as a conjunction.
- Normalize repeated bounds on one feature into the tightest interval.
- Do not report feature importance as a candidate.
- Record library version, hyperparameters, seed, and extracted node/leaf identifiers.

Polars remains the dataframe engine. Introducing a tree implementation dependency requires a
concrete dependency review; the candidate contract must not depend on a specific library.

### 4.2 Boosted-tree interaction extraction

- Use shallow base learners with maximum depth three and a fixed seed/thread policy.
- Extract path conjunctions from individual trees; aggregate identical canonical rules across
  rounds.
- Use gain/frequency only to propose an evaluation order, never as the final business rank.
- Optionally derive pairwise interaction proposals from split co-occurrence along paths.
- Recompute every rule’s support, raw difference, and exposure from the analytical dataframe;
  model-internal approximations are not numerical truth.

No boosting framework is added solely for this design. Implementation requires Architect review
of dependency, determinism, serialization, and licensing.

### 4.3 Subgroup/rule extraction

- Generate categorical equality atoms and numeric threshold atoms from fit-partition quantiles or
  other preregistered deterministic cut points.
- Evaluate one-condition rules, then expand eligible rules with beam search to depth three.
- Never combine two incompatible atoms for one feature; compatible bounds are normalized.
- Count every evaluated hypothesis, including rejected and pruned rules.
- Reject tautological expansions: every added condition must strictly reduce the parent exposure
  set.

This method is the dependency-light fallback and establishes the reference behavior against which
tree-derived candidates are tested.

## 5. Candidate evaluation and rejection

The discovery evaluator computes only descriptive quantities required for candidate screening:

- eligible population N;
- exposed and complement N;
- support;
- exposed and comparison outcome summaries;
- raw exposed-minus-comparison difference;
- harm-normalized raw difference using the supplied outcome direction;
- raw historical economic exposure only when the outcome contract supplies a valid monetary unit
  and deterministic exposure formula;
- missingness by exposure group;
- split-specific diagnostics;
- warnings and rejection reasons.

Reject rules with leakage, forbidden timing classes, identifiers, outcome-derived conditions,
unknown fields, insufficient support, empty comparison, non-harmful direction, non-finite metrics,
tautology, negligible configured materiality, or inability to reproduce the exposure mask.
Immutable-but-informative conditions may remain as diagnostic candidates only with an explicit
`actionability=REVIEW_REQUIRED` warning; they cannot outrank similarly material controllable rules
without a configured rationale.

## 6. Deduplication

Deduplication happens after canonicalization and before final ranking:

1. **Structural equality:** identical canonical conditions collapse to one candidate; provenance
   retains every source method.
2. **Logical equivalence:** redundant bounds and tautological atoms are removed; rules producing
   identical fit exposure masks collapse.
3. **Near-duplicate populations:** compute deterministic Jaccard overlap of fit exposure masks.
   Above the configured threshold, retain the shorter rule; ties prefer higher support stability,
   then controllability, then lexicographic candidate identity.
4. **Nested rules:** retain a child only if it adds preregistered incremental descriptive harm or
   materially changes the exposed population; otherwise retain the simpler parent.
5. **Family diversity:** cap cosmetic variants sharing the same dominant atom so the output is not
   filled by one broad main effect.

All discarded candidates remain counted in `evaluated_hypotheses` and receive a machine-readable
rejection reason in the run audit.

## 7. Candidate ranking interface

Ranking is a separate pure function so candidate generation cannot silently redefine business
priorities:

```python
@dataclass(frozen=True, slots=True)
class RankingInputs:
    raw_harm_magnitude: float
    raw_economic_exposure: float | None
    support: float
    temporal_stability: float | None
    segment_stability: float | None
    actionability_score: float
    novelty_score: float
    complexity_penalty: float
    warning_penalty: float

@dataclass(frozen=True, slots=True)
class RankedCandidate:
    candidate: CandidatePattern
    components: RankingInputs
    rank_score: float
    rank: int

class CandidateRanker(Protocol):
    def rank(
        self,
        candidates: Sequence[CandidatePattern],
        metrics: Mapping[str, RankingInputs],
        config: RankingConfig,
    ) -> tuple[RankedCandidate, ...]: ...
```

The score must expose every normalized component and weight. It must combine economic magnitude,
support, stability, actionability, novelty, and simplicity—not predictive importance alone.
Missing stability cannot be interpreted as stable; it produces a warning and conservative score.
Business materiality/actionability inputs must come from a Product/Statistics-approved contract,
not ML Discovery invention. Ties resolve by canonical candidate ID.

## 8. Reproducibility and run manifest

Every run records:

- run ID and immutable discovery-family ID;
- dataset version, identity hash, partition hashes, and row count;
- outcome-contract version/hash and selected primary-outcome ID supplied by that contract;
- eligible-cohort rule and harm direction;
- code commit/version and dirty-worktree flag;
- full typed configuration and canonical config hash;
- random seed, library versions, thread count, and deterministic-mode flags;
- chronological split contract/version;
- allowlisted feature names, types, and timing classifications;
- generator methods and method-specific configuration;
- exact number of evaluated hypotheses, including pruned/rejected rules;
- rejection counts by reason;
- exact immutable candidate JSON and exposure-membership digest;
- start/end timestamps and completion/failure status;
- blind-workspace bundle ID when TASK-017 applies.

Same inputs, code, config, library versions, and seed must produce byte-identical canonical
candidate content. Wall-clock timestamps live outside the canonical candidate digest.

## 9. Temporal validation hooks

Discovery fits thresholds and conditions on the designated development split only. It never edits
a rule using later outcomes.

For each immutable rule, the evaluator exposes hooks for:

- validation and future-holdout support;
- raw difference and harm direction per split;
- direction consistency;
- support drift;
- effect-magnitude drift;
- missingness drift;
- optional calendar-window diagnostics defined by the split contract.

The engine does not assign statistical significance or an evidence level. Statistics owns
uncertainty, multiple-testing correction, robustness, confounding, seasonality, and evidence
classification. The run manifest supplies the full evaluated family size needed for that work.

## 10. Required TASK-011 and TASK-013 input contract

### TASK-011 analytical dataset manifest

Required before readiness can pass:

- immutable dataset version and identity hash;
- row-aligned, separately hashed feature, outcome, identifier, and metadata partitions;
- explicit record count and row-alignment invariant;
- feature schema with dtype, nullability, and semantic classification;
- allowlist containing only `DECISION_TIME` discovery features;
- explicit exclusions for `POST_DECISION`, `OUTCOME`, `IDENTIFIER`, `METADATA`, and `UNKNOWN`;
- decision timestamp column;
- chronological split labels, boundaries, and counts;
- stable record identifier for lineage, unavailable as a feature;
- clustering key reference for later Statistics validation, unavailable as a feature;
- per-column overall and split missingness;
- transformation version/config and source/artifact hashes;
- no restricted benchmark/evaluation material in the discovery workspace.

### TASK-013 outcome contract

ML Discovery does not select the primary outcome. The supplied versioned contract must contain:

- contract version and hash;
- dataset identity it applies to;
- exactly one primary-outcome ID and physical column;
- outcome type and unit;
- explicit harmful direction/sign convention;
- eligible-cohort rule defined without post-decision selection;
- missing-data policy and required bounds/handling;
- comparison-group definition;
- deterministic raw exposure formula or an explicit statement that monetary exposure is not
  available;
- right-censoring/maturation rule where applicable;
- secondary outcomes and their permitted diagnostic/decomposition role;
- contract status `ATTACHED` or equivalent final state.

If the dataset manifest and outcome contract disagree on identity, column, status, timing, or
missingness policy, readiness fails closed. Discovery must not infer a resolution.

## 11. Output schema for 10–20 candidates

```json
{
  "schema_version": "discovery-candidates-v0",
  "status": "PERSISTED",
  "run": {
    "run_id": "uuid",
    "discovery_family_id": "sha256",
    "dataset_version": "string",
    "dataset_identity_sha256": "sha256",
    "outcome_contract_version": "string",
    "primary_outcome_id": "supplied-by-TASK-013",
    "fit_split": "development",
    "seed": 1729,
    "config_sha256": "sha256",
    "code_version": "string",
    "evaluated_hypotheses": 0,
    "blind_bundle_id": "optional-string"
  },
  "candidates": [
    {
      "candidate_id": "sha256",
      "conditions": [
        {
          "feature": "decision_time_feature",
          "operator": "ge",
          "value": 0.0,
          "feature_dtype": "Float64",
          "timing_classification": "DECISION_TIME"
        }
      ],
      "source_methods": ["subgroup_rule"],
      "population_n": 0,
      "exposed_n": 0,
      "comparison_n": 0,
      "support": 0.0,
      "raw_difference": {"value": 0.0, "unit": "from-outcome-contract"},
      "raw_harm_magnitude": {"value": 0.0, "unit": "from-outcome-contract"},
      "raw_historical_exposure": null,
      "temporal_stability": {
        "status": "NOT_EVALUATED",
        "by_split": []
      },
      "segment_stability": {
        "status": "NOT_EVALUATED",
        "by_segment": []
      },
      "actionability": "REVIEW_REQUIRED",
      "novelty": "UNASSESSED",
      "ranking": {
        "rank": 0,
        "score": 0.0,
        "components": {}
      },
      "exposure_membership_sha256": "sha256",
      "warnings": [
        "Candidate association only; causal validity not assessed."
      ]
    }
  ]
}
```

The persisted array must contain between 10 and 20 candidates. If fewer than 10 pass preregistered
eligibility, emit the smaller set with `INSUFFICIENT_ELIGIBLE_CANDIDATES`; never relax thresholds
post hoc to fill the quota. If more than 20 qualify, retain the top 20 and preserve the full search
audit and family size.

## 12. Unit-test plan

### Schema and input guards

- reject missing/mismatched dataset and outcome-contract identities;
- reject pending/unattached or multiple-primary outcome contracts;
- reject unknown, post-decision, outcome, identifier, and metadata features;
- reject broken row alignment, partition hash mismatch, or missing split labels;
- reject outcome direction/unit/missingness ambiguity;
- reject forbidden files in a blind workspace manifest.

### Rule semantics

- canonical JSON is order-independent and stable;
- equivalent numeric bounds normalize identically;
- contradictory conditions reject;
- tautological expansion rejects;
- identifiers cannot enter a condition;
- exposure mask and digest reproduce exactly;
- minimum/maximum support and comparison-size boundaries are tested at, below, and above limits;
- depth greater than three rejects.

### Candidate generators

- shallow-tree leaf paths convert to correct structured conjunctions;
- boosted path extraction merges identical rules and records provenance;
- subgroup beam search counts evaluated, pruned, and rejected hypotheses correctly;
- all generators reproduce under fixed seed and deterministic thread settings;
- generators cannot consume validation/future outcomes while fitting conditions.

### Deduplication and ranking

- structural, logical, identical-mask, nested, and high-Jaccard duplicates collapse correctly;
- shorter interpretable rule wins deterministic ties;
- ranking includes all required components and exposes weights;
- predictive importance alone cannot determine final rank;
- missing stability is penalized rather than treated as passing;
- tie-breaking is byte-stable.

### Temporal and output contract

- later-split diagnostics never mutate conditions or candidate identity;
- family size includes discarded hypotheses;
- output has 10–20 candidates or an explicit insufficiency status;
- every numeric output is recomputable from synthetic unit fixtures;
- candidate serialization contains the mandatory non-causal warning;
- rerunning identical fixture/config produces byte-identical canonical candidates.

Tests must use small transparent unit fixtures created specifically for testing. They must not read
benchmark data, hidden truth, generator code, evaluation artifacts, or private synthetic metadata.

## 13. Readiness gate

Discovery may start only when all checks pass:

- TASK-011 is closed and its immutable analytical manifest validates;
- TASK-013 is closed and its final outcome contract is attached to the exact dataset identity;
- chronological split contract is complete and exposes a development fit split plus later hooks;
- HANDOFF-007/ADR-008 access boundary is closed and a fresh allowlist-only workspace is issued;
- workspace validation confirms no restricted or extra files;
- feature timing contains no unknowns and the discovery allowlist contains only decision-time
  fields;
- output location is writable and supports immutable candidate commitment;
- full typed config, seed, dependency versions, code version, and evaluated-family accounting are
  available before data access;
- Statistics validation handoff shape is accepted.

Readiness fails closed. A failed check produces a machine-readable blocker list and no partial
discovery execution.

### Current repository readiness check

Based only on repository task/handoff metadata read for this design:

- TASK-011: closed;
- TASK-013: closed;
- HANDOFF-007: closed;
- analytical manifest/outcome attachment consistency: not ready (`HANDOFF-015` remains open);
- chronological split task: not ready (`TASK-012` remains blocked);
- current execution identity: not a fresh ADR-008 allowlist-only actor.

**Decision: NOT READY. Do not start discovery automatically.** Re-run this metadata and manifest
readiness check after the open contracts are resolved, from a fresh blind actor, before accessing
any analytical rows.
