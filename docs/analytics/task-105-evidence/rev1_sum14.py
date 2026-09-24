import json, statistics
r = json.load(open("<scratch>"))
for t in ("T01", "T02", "T04", "T05"):
    rows = [x for x in r if x["trap"] == t]
    se = [x["SE_D"] for x in rows]
    rho = [x["rho"] for x in rows]
    print(t, "n_pairs", len(rows), "H_raw", rows[0]["H_raw"], "SE_raw_boot med", statistics.median(x["SE_raw_boot"] for x in rows),
          "SE_D min/med/max", min(se), statistics.median(se), max(se), "rho min/med/max", min(rho), statistics.median(rho), max(rho),
          "c80(m10) med", round(3.417 * statistics.median(se), 1), "max", round(3.417 * max(se), 1),
          "c50(m10) med", round(2.576 * statistics.median(se), 1),
          "2*c80 med", round(2 * 3.417 * statistics.median(se), 1),
          "0.5*H_raw - c80 med", round(0.5 * rows[0]["H_raw"] - 3.417 * statistics.median(se), 1),
          "hE", rows[0]["hE"])
