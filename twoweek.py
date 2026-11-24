"""Portafoglio da ~2 trade a settimana restando profittevole.
72 gambe candidate: {Asian fade k2.5, Asian fade k2.0, Z-score z1.5, Z-score z1.0} x 18 coppie OANDA.
SCELTA 2013-2022: R>0 e t>=1 su tutto il periodo, R>0 sia 2013-17 sia 2018-22. Una variante per (famiglia, coppia).
COMPOSIZIONE: si aggiungono le gambe in ordine di t finche' la frequenza 2013-2022 arriva a 2 trade/settimana.
TEST: 2023 - nov 2026 (mai usato). Conto 50 EUR, 60 giorni, rischio 2.5 / 5 / 10%."""
import math
import numpy as np, pandas as pd
CSRC = open("combo50.py").read()
exec(CSRC[:CSRC.index("FAMS = {")])                                  # dati 18 coppie + funzioni
exec(CSRC[CSRC.index("def tstat"):CSRC.index("rows = []")])           # tstat
exec(CSRC[CSRC.index("def tm(r)"):CSRC.index("months = pd.period_range")])
exec(CSRC[CSRC.index("ENTRY = None"):CSRC.index("week = idx.to_period")])  # run_window, summary

I18 = idx.searchsorted(pd.Timestamp("2018-01-01"))
FAMS = {"Asian fade k2.5": lambda d: asian_fade(d, k=2.5), "Asian fade k2.0": lambda d: asian_fade(d, k=2.0),
        "Z-score z1.5": lambda d: zscore_fade(d, z_in=1.5), "Z-score z1.0": lambda d: zscore_fade(d, z_in=1.0)}
legs = {}
for f, fn in FAMS.items():
    for s in PIPS:
        legs[(f, s)] = [t for t in simulate(data[s], fn(data[s]), COSTS[s]) if t["entry_i"] >= I13]
weeks_sel = (idx[I23 - 1] - idx[I13]).days / 7
rows = []
for (f, s), tr in legs.items():
    R = lambda a, b: np.array([t["r"] for t in tr if a <= t["entry_i"] < b])
    a, h1, h2, te = R(I13, I23), R(I13, I18), R(I18, I23), R(I23, len(idx))
    ok = len(a) >= 20 and a.mean() > 0 and tstat(a) >= 1.0 and len(h1) and len(h2) and h1.mean() > 0 and h2.mean() > 0
    rows.append(dict(variante=f, simbolo=s, famiglia=f.split(" k")[0].split(" z")[0], n_13_22=len(a), trade_sett=round(len(a) / weeks_sel, 3),
                     r_13_22=round(a.mean(), 3) if len(a) else None, t_13_22=round(tstat(a), 2),
                     r_13_17=round(h1.mean(), 3) if len(h1) else None, r_18_22=round(h2.mean(), 3) if len(h2) else None,
                     n_23_26=len(te), r_23_26=round(te.mean(), 3) if len(te) else None, t_23_26=round(tstat(te), 2), scelta=bool(ok)))
L = pd.DataFrame(rows)
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 100); pd.set_option("display.max_columns", 30)
C = L[L.scelta].sort_values("t_13_22", ascending=False)
print("=== Gambe che superano la scelta 2013-2022 ===\n" + C.to_string(index=False))

chosen, freq, used = [], 0.0, set()
for r in C.itertuples():
    if (r.famiglia, r.simbolo) in used: continue
    chosen.append((r.variante, r.simbolo)); used.add((r.famiglia, r.simbolo)); freq += r.trade_sett
    if freq >= 2.0: break
print(f"\nPortafoglio composto ({len(chosen)} gambe, {freq:.2f} trade/settimana nel 2013-2022):", [f"{a} {b}" for a, b in chosen])
L.to_csv("results/twoweek_legs.csv", index=False)


def trades_of(keys, a, b):
    return sorted([t for k in keys for t in legs[k] if a <= t["entry_i"] < b], key=lambda t: t["entry_i"])


PORTS = {"Attuale (Asian EURCHF + Z EURGBP)": [("Asian fade k2.5", "EURCHF"), ("Z-score z1.5", "EURGBP")], "Nuovo (2 trade/settimana)": chosen}
out = {}
for per, (a, b) in {"scelta 2013-22": (I13, I23), "TEST 2023-26": (I23, len(idx))}.items():
    wk = (idx[b - 1] - idx[a]).days / 7
    for name, keys in PORTS.items():
        tr = trades_of(keys, a, b); m = tm([t["r"] for t in tr])
        m["trade/settimana"] = round(len(tr) / wk, 2)
        ev = sorted([(t["entry_i"], 1) for t in tr] + [(t["exit_i"], -1) for t in tr]); c = mx = 0
        for _, d in ev: c += d; mx = max(mx, c)
        m["max posizioni insieme"] = mx
        out[f"{name} | {per}"] = m
print("\n=== Metriche per trade ===\n" + pd.DataFrame(out).to_string())

print("\nGambe del portafoglio nel TEST 2023-26:")
print(L.set_index(["variante", "simbolo"]).loc[chosen, ["n_23_26", "r_23_26", "t_23_26"]].to_string())

week = idx.to_period("W").asi8; st = np.r_[0, np.flatnonzero(np.diff(week)) + 1]
S = {}
for per, (a, b) in {"scelta 2013-22": (I13, I23), "TEST 2023-26": (I23, len(idx))}.items():
    sts = st[(st >= a) & (st < b) & (idx[st] <= idx[min(b, len(idx)) - 1] - pd.Timedelta(days=80))]
    for name, keys in PORTS.items():
        tr = trades_of(keys, a, len(idx)); ent = np.array([t["entry_i"] for t in tr])
        for lab, kw in [("2,5%", dict(base=0.025)), ("5%", dict(base=0.05)), ("10%", {})]:
            S[f"{per} | {name} | {lab}"] = summary(pd.DataFrame([run_window(tr, ent, s, **kw) for s in sts]))
print("\n=== Conto 50 EUR, 60 giorni (anti-martingala x1,5 max x3) ===\n" + pd.DataFrame(S).T.to_string())
pd.DataFrame(S).T.to_csv("results/twoweek_test.csv")
