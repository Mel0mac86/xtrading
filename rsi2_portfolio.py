"""RSI(2) dip-buy su tutti i 15 indici (nessuna selezione per indice) + le 2 strategie forex.
Metriche per periodo e conto da 100 EUR (P/L contabilizzato alla chiusura dei trade).
Costi indici: spread 0,02% + finanziamento 5% annuo."""
import math, heapq
import numpy as np, pandas as pd
import daily_search as D

data = {s: D.load(s) for s in D.IDX}
rsi_tr = []
for s in D.IDX:
    for t in D.simulate(data[s], D.rsi2(data[s]), D.SPREAD[s]):
        t["strategia"] = "RSI2 indici"; t["sym"] = s; rsi_tr.append(t)
# strategie forex (H1) dal backtest aggr50
A = open("aggr50.py").read(); g = {}
exec(A[:A.index("# ---------------------------------------------------------------- 1) quanti trade")], g)
fx_tr = [dict(strategia=t["strategia"], sym=t["strategia"].split()[-1], entry=g["idx"][t["entry_i"]].normalize(),
              exit=g["idx"][min(t["exit_i"], len(g["idx"]) - 1)].normalize(), r=t["r"]) for t in g["trades"]]
ALL = sorted(rsi_tr + fx_tr, key=lambda t: t["entry"])
P = {"2013-2019": ("2013-01-01", "2020-01-01"), "2020-2022": ("2020-01-01", "2023-01-01"), "2023-2026": ("2023-01-01", "2027-01-01")}
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 100); pd.set_option("display.max_columns", 30)

print("=== RSI2 per indice (guadagno medio per trade, R) ===")
rows = []
for s in D.IDX:
    row = {"indice": s}
    for p, (a, b) in P.items():
        r = np.array([t["r"] for t in rsi_tr if t["sym"] == s and pd.Timestamp(a) <= t["entry"] < pd.Timestamp(b)])
        row[p] = f"{r.mean():+.3f} ({len(r)})" if len(r) else "-"
    rows.append(row)
print(pd.DataFrame(rows).to_string(index=False))


def tm(tr, a, b):
    r = np.array([t["r"] for t in tr if pd.Timestamp(a) <= t["entry"] < pd.Timestamp(b)]); w, l = r[r > 0], r[r <= 0]
    s = mx = 0
    for x in r: s = s + 1 if x <= 0 else 0; mx = max(mx, s)
    t = D.tstat(r); months = (pd.Timestamp(min(b, "2026-11-24")) - pd.Timestamp(a)).days / 30.44
    return {"trade": len(r), "trade/mese": round(len(r) / months, 1), "vincenti %": round(len(w) / len(r) * 100, 1), "R medio": round(r.mean(), 3),
            "vincita media R": round(w.mean(), 2), "perdita media R": round(l.mean(), 2), "profit factor": round(w.sum() / -l.sum(), 2),
            "max perdite di fila": mx, "t-stat": round(t, 2), "p-value": round(math.erfc(abs(t) / math.sqrt(2)), 4)}


SETS = {"RSI2 15 indici": rsi_tr, "Forex 2 strategie": fx_tr, "TUTTE (RSI2 + forex)": ALL}
M = {f"{n} | {p}": tm(tr, a, b) for n, tr in SETS.items() for p, (a, b) in P.items()}
print("\n=== METRICHE PER TRADE ===\n" + pd.DataFrame(M).to_string())


def account(tr, start, end, cap=100.0, risk=0.02, max_open=None):
    """P/L alla chiusura; rischio fisso in % del capitale iniziale; opzionale tetto di posizioni aperte."""
    sel = sorted([t for t in tr if pd.Timestamp(start) <= t["entry"] < pd.Timestamp(end)], key=lambda t: t["entry"])  # ordine cronologico
    taken, open_exits = [], []
    for t in sel:
        open_exits = [e for e in open_exits if e > t["entry"]]
        if max_open and len(open_exits) >= max_open: continue
        taken.append(t); open_exits.append(t["exit"])
    pnl = pd.Series([cap * risk * t["r"] for t in taken], index=[t["exit"] for t in taken]).groupby(level=0).sum().sort_index()
    days = pd.bdate_range(start, min(pd.Timestamp(end), pd.Timestamp("2026-11-24")))
    eq = cap + pnl.reindex(days, fill_value=0).cumsum()
    peak = eq.cummax(); dd = (peak - eq).max()
    mon = eq.groupby(eq.index.to_period("M")).last(); mret = mon.diff().fillna(mon.iloc[0] - cap)
    r = np.array([cap * risk * t["r"] for t in taken])
    ev = sorted([(t["entry"], 1) for t in taken] + [(t["exit"], -1) for t in taken]); c = mx = 0
    for _, d in ev: c += d; mx = max(mx, c)
    return {"capitale finale EUR": round(eq.iloc[-1], 2), "rendimento %": round((eq.iloc[-1] / cap - 1) * 100, 1),
            "minimo EUR": round(eq.min(), 2), "drawdown max EUR": round(dd, 2), "drawdown max %": round(dd / peak[eq.idxmax() if False else peak.idxmax()] * 100, 1),
            "trade": len(r), "trade/mese": round(len(r) / max(len(mret), 1), 1), "vincenti %": round((r > 0).mean() * 100, 1),
            "miglior trade EUR": round(r.max(), 2), "peggior trade EUR": round(r.min(), 2),
            "mesi positivi": f"{int((mret > 0).sum())}/{len(mret)}", "miglior mese EUR": round(mret.max(), 2), "peggior mese EUR": round(mret.min(), 2),
            "max posizioni aperte": mx}, mret


print("\n=== CONTO DA 100 EUR (rischio 2% = 2 EUR a trade, max 6 posizioni aperte) ===")
R, MON = {}, {}
for per, (a, b) in {"2023 - nov 2026": ("2023-01-01", "2027-01-01"), "gen - nov 2026": ("2026-01-01", "2027-01-01")}.items():
    for n, tr in SETS.items():
        m, mret = account(tr, a, b, risk=0.02, max_open=6); R[f"{n} | {per}"] = m
        if per.startswith("gen"): MON[n] = mret.round(2)
print(pd.DataFrame(R).to_string())
eqm = pd.DataFrame(MON); eqm.index = eqm.index.astype(str)
print("\n=== 2026 mese per mese (EUR, rischio 2%) ===\n" + eqm.to_string())
print("\nCapitale a fine mese:\n" + (eqm.cumsum() + 100).round(2).to_string())
pd.DataFrame(M).to_csv("results/rsi2_metrics.csv"); pd.DataFrame(R).to_csv("results/rsi2_account.csv")
