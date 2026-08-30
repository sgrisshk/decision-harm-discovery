"""TASK-080 second revision (`ADR-077`) — supplementary n-sweep isolating the T-odds-asymmetry
symmetry-breaking axis in isolation from confounder-prevalence skew (`u_prior=0.5` throughout,
so the 1e panel of `diagnose_task080_identifiability_suite.py` is reused verbatim, not reproduced).

`diagnose_task080_identifiability_suite.py`'s own 1e panel (n=3200 only) found the ADR-075
classifier's `interaction_like` rate stayed at 0/40 across every tested non-complementary T-odds
pair at that one sample size — this looked, at first glance, like the odds-asymmetry axis might not
share direction 1's headline growth-with-n property. Section 2a's closed-form derivation
(`_analytic_bias_function`/`_stratum_prevalence`) already proves the TRUE delta is nonzero for every
non-complementary-odds case tested — the open empirical question this script answers is only whether
that true, nonzero bias eventually crosses the classifier's own significance/stability bar as n
grows, exactly as it did for the confounder-prevalence axis in 1a. Uses a larger odds asymmetry
(0.95/0.35, delta ~71.5 analytically, vs. 1e's own largest gap ~32) so the effect has enough leverage
to observe the trend at n values that keep runtime small.

Imports and reuses `gen_confound_binary`/`classify_atom`/`_analytic_bias_function`/
`_stratum_prevalence` from the sibling script verbatim — no DGP or classifier logic is
reimplemented here.

Usage:
  uv run python scripts/diagnose_task080_odds_asymmetry_nsweep.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parent
sys.path.insert(0, str(REPOSITORY))

from diagnose_task080_identifiability_suite import (  # noqa: E402
    _analytic_bias_function,
    _stratum_prevalence,
    classify_atom,
    gen_confound_binary,
)


def main() -> None:
    u_prior = 0.5
    concordance = 0.85
    t_odds_hi, t_odds_lo = 0.95, 0.35  # non-complementary (sum=1.3)
    confound_strength = 220.0

    q_t, q_c = _stratum_prevalence(u_prior, concordance)
    true_delta = _analytic_bias_function(
        q_t, t_odds_hi, t_odds_lo, confound_strength
    ) - _analytic_bias_function(q_c, t_odds_hi, t_odds_lo, confound_strength)
    print("=" * 100)
    print("Supplementary: pure T-odds-asymmetry axis (u_prior=0.5 fixed), n-sweep")
    print("=" * 100)
    print(
        f"u_prior={u_prior}, concordance={concordance}, odds=({t_odds_hi},{t_odds_lo}) "
        f"[non-complementary, sum={t_odds_hi + t_odds_lo}]"
    )
    print(f"Analytic true delta (closed form, infinite-sample): {true_delta:.2f}")
    print()

    n_points = [800, 1600, 3200, 6400, 12800, 25600]
    rows = []
    for n in n_points:
        trials = 40
        interaction_count = 0
        for trial in range(trials):
            frame = gen_confound_binary(
                n,
                u_prior=u_prior,
                concordance=concordance,
                t_odds_hi=t_odds_hi,
                t_odds_lo=t_odds_lo,
                confound_strength=confound_strength,
                noise_sd=60.0,
                seed=4_000_000 + n + trial,
            )
            r = classify_atom(frame)
            if r.label_v075 == "interaction_like":
                interaction_count += 1
        rate = interaction_count / trials
        rows.append({"n": n, "trials": trials, "interaction_like_count": interaction_count, "interaction_like_rate": rate})
        print(f"  n={n:>6}  interaction_like={interaction_count:>3}/{trials} = {rate:.3f}")

    out = {
        "u_prior": u_prior,
        "concordance": concordance,
        "t_odds_hi": t_odds_hi,
        "t_odds_lo": t_odds_lo,
        "confound_strength": confound_strength,
        "analytic_true_delta": true_delta,
        "n_sweep": rows,
    }
    out_path = REPOSITORY.parent / "docs/benchmark/task-080-odds-asymmetry-nsweep-raw.json"
    out_path.write_text(json.dumps(out, indent=2))
    print()
    print(f"Raw output written to {out_path}")


if __name__ == "__main__":
    main()
