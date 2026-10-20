"""Figures for the complement-contamination, exponent and trajectory analyses. Every number is read from committed evidence or from this directory's raw
analysis output; nothing is typed in except where a source table is quoted (marked SOURCE).

  uv run --with matplotlib python figures.py [name ...]
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

import matplotlib

matplotlib.use("pdf")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
FIG = HERE / "figures"
FIG.mkdir(exist_ok=True)

INK, INK2, MUTED, GRID = "#0b0b0b", "#52514e", "#8a8984", "#e4e3de"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"  # validated categorical slots 1-3

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["CMU Serif", "Computer Modern Roman", "Times New Roman", "DejaVu Serif"],
    "mathtext.fontset": "cm",
    "font.size": 8.5,
    "axes.titlesize": 8.5,
    "axes.labelsize": 8.5,
    "axes.edgecolor": MUTED,
    "axes.labelcolor": INK,
    "axes.linewidth": 0.6,
    "xtick.color": INK2,
    "ytick.color": INK2,
    "xtick.major.width": 0.6,
    "ytick.major.width": 0.6,
    "legend.frameon": False,
    "legend.fontsize": 8,
    "pdf.fonttype": 42,
})

CORE = ["C02", "C04", "C06", "C07", "C08", "C09", "C11", "C12", "C14", "C15", "H01"]


def clean(ax: plt.Axes, grid_axis: str = "x") -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.grid(axis=grid_axis, color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def save(fig: plt.Figure, name: str) -> None:
    fig.savefig(FIG / f"{name}.pdf", bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)
    print("wrote", FIG / f"{name}.pdf")


# ---------------------------------------------------------------------------------------------
def fig_recovery() -> None:
    agg = json.loads((REPO / "docs/benchmark/task-109-evidence/engine-aggregate-rates.json").read_text())
    per = agg["core"]["per_target_k_of_30"]
    first = {t: (per[t]["coverage_k_of_n"], per[t]["specific_k_of_n"], per[t]["exact_k_of_n"]) for t in CORE}
    reserve: dict[str, tuple[int, int, int]] = {}
    for f in sorted((REPO / "docs/benchmark/task-112-evidence/step5-paired-4101-4130").glob("baseline-seed-*.json")):
        d = json.loads(f.read_text())
        core = d["score"]["strata"]["core"]
        for t in CORE:
            c, s, e = reserve.get(t, (0, 0, 0))
            reserve[t] = (c + (t in core["coverage_targets"]),
                          s + (t in core["specific_targets"]["0.50"]),
                          e + (t in core["exact_targets"]))
    order = sorted(CORE, key=lambda t: (first[t][1] + reserve[t][1], t))
    fig, axes = plt.subplots(1, 2, figsize=(6.3, 2.9), sharey=True)
    styles = [("Coverage", BLUE, "o", 0.18), ("Specific", ORANGE, "D", 0.0), ("Exact", AQUA, "s", -0.18)]
    for ax, data, title in ((axes[0], first, "Evaluation seeds 4001–4030"),
                            (axes[1], reserve, "Reserve seeds 4101–4130")):
        for i, t in enumerate(order):
            ax.plot([0, 30], [i, i], color=GRID, linewidth=0.6, zorder=0)
            for j, (name, col, mk, off) in enumerate(styles):
                ax.plot(data[t][j], i + off, marker=mk, color=col, markersize=4.6, linestyle="none",
                        markeredgecolor="white", markeredgewidth=0.6, label=name if i == 0 else None)
        ax.axvline(30, color=INK2, linewidth=0.7, linestyle=(0, (2, 2)))
        ax.set_xlim(-1, 31)
        ax.set_xticks([0, 10, 20, 30])
        ax.set_xlabel("seeds recovered (of 30)")
        ax.set_title(title, color=INK, loc="left")
        clean(ax)
    axes[0].set_yticks(range(len(order)))
    axes[0].set_yticklabels(order)
    axes[0].set_ylim(-0.6, len(order) - 0.4)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, bbox_to_anchor=(0.5, -0.04),
               handletextpad=0.3, columnspacing=1.6)
    fig.tight_layout(w_pad=1.2, rect=(0, 0.06, 1, 1))
    save(fig, "recovery")


# ---------------------------------------------------------------------------------------------
def fig_logdecomp() -> None:
    d = json.loads((REPO / "docs/benchmark/task-111-evidence/h111-analysis-summary.json").read_text())
    rows = []
    for t in ["C02", "C04", "C06", "C09", "C11", "C12", "C14", "C15", "H01", "C08"]:
        m = d["targets"][t]["vs_named_competitor"]["mean_log_decomp"]
        rows.append((t, m["harm_contrib"], m["population_contrib"], m["complexity_contrib"]))
    fig, ax = plt.subplots(figsize=(6.3, 2.5))
    width = 0.26
    xs = range(len(rows))
    for k, (name, col) in enumerate([("harm term", ORANGE), ("population term  ½Δln n", BLUE),
                                     ("complexity term", AQUA)]):
        vals = [r[k + 1] for r in rows]
        ax.bar([x + (k - 1) * width for x in xs], vals, width=width - 0.03, color=col, label=name,
               linewidth=0)
    totals = [r[1] + r[2] + r[3] for r in rows]
    ax.plot(list(xs), totals, linestyle="none", marker="_", markersize=11, markeredgewidth=1.6,
            color=INK, label="total  ln S(B) − ln S(P)")
    ax.axhline(0, color=INK2, linewidth=0.7)
    ax.set_xticks(list(xs))
    ax.set_xticklabels([r[0] for r in rows])
    ax.set_ylabel("mean log contribution (nats)")
    ax.legend(ncol=4, loc="upper center", bbox_to_anchor=(0.5, 1.2), columnspacing=1.0, handlelength=1.2)
    clean(ax, "y")
    save(fig, "logdecomp")


# ---------------------------------------------------------------------------------------------
def closed_form_delta(p: float, c: float, t1: float, t0: float, s: float) -> float:
    def f(q: float) -> float:
        a = q * t1 / (q * t1 + (1 - q) * t0)
        b = q * (1 - t1) / (q * (1 - t1) + (1 - q) * (1 - t0))
        return s * (a - b)
    qp = c * p / (c * p + (1 - c) * (1 - p))
    qm = (1 - c) * p / ((1 - c) * p + c * (1 - p))
    return f(qp) - f(qm)


def fig_ident() -> None:
    # SOURCE: docs/analytics/task-080-candidate-composition-safety-design.md section 15.1.1
    ns = [300, 600, 1200, 2400, 4800, 9600, 12800]
    rate = [0.067, 0.400, 0.783, 1.000, 1.000, 1.000, 1.000]
    fig, axes = plt.subplots(1, 2, figsize=(6.3, 2.3))
    ax = axes[0]
    ax.plot(ns, rate, color=BLUE, linewidth=2, marker="o", markersize=4.5, markeredgecolor="white")
    ax.axhline(0.05, color=INK2, linewidth=0.7, linestyle=(0, (2, 2)))
    ax.text(330, 0.09, "a Type I error would stay here", fontsize=7, color=INK2)
    ax.set_xscale("log")
    ax.set_xticks(ns[::2] + [12800])
    ax.set_xticklabels([f"{n:,}" for n in ns[::2] + [12800]])
    ax.set_ylim(0, 1.05)
    ax.set_xlabel("sample size $n$")
    ax.set_ylabel("share classified 'interaction'")
    ax.set_title("(a) Pure confounding, true effect 0", loc="left")
    clean(ax, "y")
    ax = axes[1]
    ps = [i / 200 for i in range(2, 199)]
    for (t1, t0), col, name in [((0.75, 0.25), BLUE, "complementary odds (0.75, 0.25)"),
                                ((0.8, 0.4), ORANGE, "non-complementary (0.80, 0.40)")]:
        ax.plot(ps, [closed_form_delta(p, 0.75, t1, t0, 220) for p in ps], color=col, linewidth=2, label=name)
    ax.axhline(0, color=INK2, linewidth=0.7)
    ax.axvline(0.5, color=MUTED, linewidth=0.6, linestyle=(0, (2, 2)))
    ax.set_xlabel("confounder prevalence $p$")
    ax.set_ylabel(r"$f(q_+) - f(q_-)$")
    ax.set_title("(b) Estimand under pure confounding", loc="left")
    ax.legend(loc="lower left", fontsize=7, handlelength=1.4)
    clean(ax, "y")
    fig.tight_layout(w_pad=1.5)
    save(fig, "identification")


# ---------------------------------------------------------------------------------------------
def fig_operating() -> None:
    ps = [i / 400 for i in range(0, 401)]
    fig, ax = plt.subplots(figsize=(3.1, 2.3))
    ax.plot(ps, [1 - (1 - p) ** 30 for p in ps], color=BLUE, linewidth=2)
    ax.plot(ps, [p ** 30 for p in ps], color=ORANGE, linewidth=2)
    ax.text(0.16, 0.86, "'ever' ($\\geq$1/30)", color=INK, fontsize=7.5)
    ax.text(0.40, 0.08, "'reliable' (30/30)", color=INK, fontsize=7.5)
    ax.set_xlabel("true per-seed recovery probability")
    ax.set_ylabel("probability target is counted")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.02)
    clean(ax, "y")
    save(fig, "operating")


# ---------------------------------------------------------------------------------------------
def fig_contamination() -> None:
    data = json.loads((HERE / "contamination-raw.json").read_text())
    # single-literal marginal contrasts: alone vs composite, every Core target with >= 2 literals
    alone, comp, colours = [], [], []
    flips = {"alone_neg": 0, "comp_neg": 0, "n": 0}
    for seed in data:
        for t, block in seed["targets"].items():
            keys = [k for k in block["alone"] if " & " not in k]
            if len(block["alone"]) == 1:
                continue
            for k in keys:
                a, c = block["alone"][k]["harm"], block["composite"][k]["harm"]
                alone.append(a)
                comp.append(c)
                colours.append(ORANGE if t == "C02" else BLUE)
                flips["n"] += 1
                flips["alone_neg"] += a <= 0
                flips["comp_neg"] += c <= 0
    fig, axes = plt.subplots(1, 2, figsize=(6.3, 2.6))
    ax = axes[0]
    ax.scatter(alone, comp, s=7, c=colours, linewidths=0, alpha=0.75)
    lo = min(alone + comp)
    hi = max(alone + comp)
    ax.plot([lo, hi], [lo, hi], color=MUTED, linewidth=0.6, linestyle=(0, (2, 2)))
    ax.axhline(0, color=INK2, linewidth=0.7)
    ax.axvline(0, color=INK2, linewidth=0.7)
    ax.set_xlabel("literal contrast, target planted alone (€)")
    ax.set_ylabel("same literal, 20-target composite (€)")
    ax.set_title("(a) Every true literal, every seed", loc="left")
    ax.text(0.98, 0.04, "C02 literals", color=ORANGE, transform=ax.transAxes, ha="right", fontsize=7)
    clean(ax, "y")
    ax = axes[1]
    c02 = [s["targets"]["C02"] for s in data]
    names = list(c02[0]["alone"])
    pos = range(len(names))
    for j, (cond, col, mk) in enumerate([("none", MUTED, "o"), ("alone", BLUE, "D"), ("composite", ORANGE, "s")]):
        means = [statistics.mean(b[cond][n]["harm"] for b in c02) for n in names]
        sds = [statistics.stdev(b[cond][n]["harm"] for b in c02) for n in names]
        ax.errorbar([p + (j - 1) * 0.2 for p in pos], means, yerr=sds, fmt=mk, color=col, markersize=4,
                    elinewidth=0.8, capsize=0, label={"none": "no target", "alone": "C02 alone",
                                                      "composite": "all 20"}[cond])
    ax.axhline(0, color=INK2, linewidth=0.7)
    ax.set_xticks(list(pos))
    ax.set_xticklabels([n.replace("destination eq ", "").replace("customer_segment eq ", "")
                        .replace(" & ", r" $\wedge$ ") for n in names], fontsize=7.5)
    ax.set_ylabel("contrast Δ (€, mean ± sd over seeds)")
    ax.set_title("(b) C02 under common random numbers", loc="left")
    ax.legend(loc="upper left", fontsize=7)
    clean(ax, "y")
    fig.tight_layout(w_pad=1.5)
    save(fig, "contamination")
    (HERE / "contamination-summary.json").write_text(json.dumps(flips, indent=1) + "\n")
    print(flips)


# ---------------------------------------------------------------------------------------------
def fig_alpha() -> None:
    data = json.loads((HERE / "alpha-sweep-raw.json").read_text())
    alphas = sorted({d["alpha"] for d in data})
    cov, spec, size, ntc = [], [], [], []
    summary = {}
    for a in alphas:
        runs = [d for d in data if d["alpha"] == a]
        cov.append(statistics.mean(len(d["coverage_targets"]) for d in runs))
        spec.append(statistics.mean(len(d["metric_specific_targets"]) for d in runs))
        cands = [c for d in runs for c in d["candidates"]]
        size.append(statistics.median(c["n_exposed_development"] for c in cands))
        ntc.append(statistics.mean(c["n_targets_covered"] for c in cands))
        summary[str(a)] = {"mean_coverage_targets": cov[-1], "mean_metric_specific_targets": spec[-1],
                           "median_n_exposed": size[-1], "mean_targets_covered_per_candidate": ntc[-1],
                           "n_seeds": len(runs)}
    fig, axes = plt.subplots(1, 2, figsize=(6.3, 2.4))
    ax = axes[0]
    ax.plot(alphas, cov, color=BLUE, linewidth=2, marker="o", markersize=4.5, markeredgecolor="white")
    ax.plot(alphas, spec, color=ORANGE, linewidth=2, marker="D", markersize=4.2, markeredgecolor="white")
    ax.text(alphas[-1], cov[-1] + 0.4, "Coverage", ha="right", fontsize=7.5)
    ax.text(0.5, max(spec) + 0.5, "Specific (metric part)", ha="center", fontsize=7.5)
    ax.set_ylim(0, 11.5)
    ax.set_xlabel(r"volume exponent $\alpha$")
    ax.set_ylabel("Core targets per seed (of 11)")
    ax.set_title("(a) Recovery", loc="left")
    ax.axvline(0.5, color=MUTED, linewidth=0.6, linestyle=(0, (2, 2)))
    clean(ax, "y")
    ax = axes[1]
    ax.plot(alphas, size, color=BLUE, linewidth=2, marker="o", markersize=4.5, markeredgecolor="white")
    ax.set_yscale("log")
    ax.set_xlabel(r"volume exponent $\alpha$")
    ax.set_ylabel("median exposed rows (development)")
    ax.set_title("(b) Size of selected rules", loc="left")
    ax.axvline(0.5, color=MUTED, linewidth=0.6, linestyle=(0, (2, 2)))
    clean(ax, "y")
    fig.tight_layout(w_pad=1.5)
    save(fig, "alpha")
    (HERE / "alpha-summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps(summary, indent=1))


# ---------------------------------------------------------------------------------------------
def fig_task117() -> None:
    files = sorted((REPO / "docs/benchmark/task-117-evidence/raw").glob("seed-*.json"))
    data = [json.loads(f.read_text()) for f in files]
    targets = ["C04", "C06", "C09", "C14", "C15"]
    fig, ax = plt.subplots(figsize=(6.3, 2.3))
    for i, t in enumerate(targets):
        vals = [d["targets"][t]["best_productive_scored"]["ratio_to_15th_selected"]
                for d in data if "best_productive_scored" in d["targets"][t]
                and not d["targets"][t]["baseline_specific_task109"]]
        restored = [d["targets"][t]["counterfactual"].get("restored_specific") for d in data
                    if "best_productive_scored" in d["targets"][t]
                    and not d["targets"][t]["baseline_specific_task109"]]
        jitter = [((k * 37) % 11 - 5) / 40 for k in range(len(vals))]
        ax.scatter([v for v in vals], [i + j for j in jitter], s=12,
                   c=[BLUE if r else ORANGE for r in restored], linewidths=0)
    ax.axvline(1.0, color=INK2, linewidth=0.7, linestyle=(0, (2, 2)))
    ax.text(1.0, len(targets) - 0.45, " score of 15th selected rule", fontsize=7, color=INK2, va="top")
    ax.set_yticks(range(len(targets)))
    ax.set_yticklabels(targets)
    ax.set_xscale("log")
    ax.set_xlabel("effective score of best productive rule ÷ score of last selected rule")
    ax.scatter([], [], s=12, c=BLUE, label="one-step replay restores Specific")
    ax.scatter([], [], s=12, c=ORANGE, label="not restored")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.32), ncol=2, fontsize=7.5)
    clean(ax)
    save(fig, "task117")


# ---------------------------------------------------------------------------------------------
def fig_perseed() -> None:
    counts = json.loads((HERE / "per-seed-counts.json").read_text())
    fig, axes = plt.subplots(1, 2, figsize=(6.3, 2.3), sharey=True)
    for ax, key, title in ((axes[0], "4001", "Evaluation seeds 4001–4030"),
                           (axes[1], "4101", "Reserve seeds 4101–4130")):
        width = 0.27
        for j, (lvl, name, col) in enumerate([("cov", "Coverage", BLUE), ("spec", "Specific", ORANGE),
                                              ("ex", "Exact", AQUA)]):
            vals = counts[f"{key}-{lvl}"]
            xs = list(range(0, 12))
            ys = [vals.count(x) for x in xs]
            ax.bar([x + (j - 1) * width for x in xs], ys, width=width - 0.03, color=col, label=name,
                   linewidth=0)
        ax.set_xticks(range(0, 12))
        ax.set_xlabel("Core targets recovered on a seed (of 11)")
        ax.set_title(title, loc="left")
        clean(ax, "y")
    axes[0].set_ylabel("number of seeds")
    axes[1].legend(loc="upper center", fontsize=7.5)
    fig.tight_layout(w_pad=1.2)
    save(fig, "perseed")


if __name__ == "__main__":
    names = sys.argv[1:] or ["recovery", "logdecomp", "ident", "operating"]
    for n in names:
        globals()[f"fig_{n}"]()
