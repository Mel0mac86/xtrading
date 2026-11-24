"""Rischio in EUR di un trade a 0,01 lotti (1.000 unita') nel 2026, per capire quale capitale serve su un conto standard."""
import numpy as np, pandas as pd
A = open("aggr50.py").read()
exec(A[:A.index("# ---------------------------------------------------------------- 1) quanti trade")])
s0 = idx.searchsorted(pd.Timestamp("2026-01-01"))
gbp_eur = 1 / data["EURGBP"]["close"].iloc[-1]; chf_eur = 1 / data["EURCHF"]["close"].iloc[-1]
rows = []
for name, s, fn, q in [("Asian fade EURCHF", "EURCHF", asian_fade, chf_eur), ("Z-score fade EURGBP", "EURGBP", zscore_fade, gbp_eur)]:
    sp = fn(data[s]); sd = np.array([sp["stop_dist"][t["entry_i"] - 1] for t in trades if t["entry_i"] >= s0 and t["strategia"] == name])
    eur = (sd + COST[s]) * 1000 * q      # 0,01 lotti = 1.000 unita' della valuta base; P/L in valuta quotata -> EUR
    rows.append(dict(strategia=name, trade_2026=len(sd), stop_pips_mediano=round(np.median(sd) * 1e4, 1),
                     rischio_minimo_EUR_mediano=round(np.median(eur), 2), rischio_minimo_EUR_max=round(eur.max(), 2)))
print(pd.DataFrame(rows).to_string(index=False))
