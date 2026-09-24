from statistics import NormalDist as N
import math
nd = N()
z80 = nd.inv_cdf(0.8)
print("z80", round(z80, 4))
for m in (3, 7, 10, 15):
    zc = nd.inv_cdf(1 - 0.10 / (2 * m))
    print("m", m, "zcrit", round(zc, 3), "zcrit+z80", round(zc + z80, 3), "per-test level", 0.1 / (2 * m))
rows = {"T01": 35, "T02": 36, "T04": 34, "T05": 59}
for k, se in rows.items():
    for m in (7, 10):
        zc = nd.inv_cdf(1 - 0.10 / (2 * m))
        out = []
        for rho in (0.55, 0.70, 1.0):
            out.append((rho, round(zc * rho * se), round((zc + z80) * rho * se)))
        print(k, "m", m, "(rho, 50%pw crit, 80%pw floor)", out)
print("hE/sd", math.log(1.125) / 0.91, "RR*", 1.5 ** 2 / (2 * 1.5 - 1))
print("hE at sd 776", math.log(1.125) / 0.91 * 776)
