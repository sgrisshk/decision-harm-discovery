import json
r = json.load(open("<scratch>"))
print("cell | block_rate (blocks/2000) | Z1 P(p_att<=.05) | <=.01 | <=.005 | E applicable | P(p_E<=.05|appl) | <=.01 | mean Hz | mean Hraw | mean SE(D)")
for k, v in r.items():
    f = lambda x: "-" if x is None else f"{x:.4f}"
    print(k, "|", f"{v['block_rate']:.4f} ({v['blocks']})", "|", f(v["z1_p_att_le_005"]), "|", f(v["z1_p_att_le_001"]), "|", f(v["z1_p_att_le_0005"]),
          "|", f(v["z1_E_applicable"]), "|", f(v["z1_p_E_le_005_given_applicable"]), "|", f(v["z1_p_E_le_001_given_applicable"]),
          "|", round(v["z1_mean_Hz"], 1), "|", round(v["z1_mean_Hraw"], 1), "|", round(v["z1_mean_seD"], 1))
