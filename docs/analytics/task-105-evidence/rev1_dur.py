import sys, bisect, collections
sys.path.insert(0, "<scratch>")
import polars as pl
from rev1_common import load_delivered, quantile_breakpoints
df = load_delivered()
dev = df.filter(pl.col("split_label") == "development")
for col, cut in (("trip_duration_days", 14), ("booking_lead_days", 14)):
    vals = [v for v in dev[col].to_list()]
    bp = quantile_breakpoints(vals, 10)
    print(col, "distinct dev", len(set(vals)), "dev decile edges", bp, "min/max", min(vals), max(vals))
    allv = df[col].to_list()
    bins = collections.defaultdict(lambda: [0, 0])
    for v in allv:
        b = bisect.bisect_right(bp, v)
        bins[b][0] += 1
        bins[b][1] += int((v >= 14) if col == "trip_duration_days" else (v < 14))
    for b in sorted(bins):
        n, k = bins[b]
        print("  bin", b, "n", n, "indicator share", round(k / n, 3))
    q = quantile_breakpoints(vals, 4)
    print("  G06 quartile edges", q)
