"""Combinare piu' strategie/strumenti per avere piu' trade con vantaggio (dati OANDA H1).
Strategie fisse (nessuna ottimizzazione): Asian fade (k 2.5) e Z-score fade D1 (n 50, z 1.5) su 18 coppie.
Protocollo deciso prima di vedere i risultati:
  SCELTA 2013-2019: gamba tenuta se n>=15, R medio>0, t>=1
  CONFERMA 2020-2022: R medio > 0
  TEST 2023 - nov 2026: combinazione nuova contro le 2 gambe attuali; conto 50 EUR."""
import math, heapq
import numpy as np, pandas as pd
src = open("aggr50.py").read(); exec(src[:src.index("# ---------------------------------------------------------------- dati e trade")])

PIPS = {"EURUSD": 1.0, "GBPUSD": 1.5, "USDCHF": 1.6, "USDCAD": 1.8, "AUDUSD": 1.4, "NZDUSD": 1.8, "EURGBP": 1.8, "EURCHF": 2.2,
        "GBPCHF": 3.0, "AUDNZD": 2.8, "CADCHF": 2.8, "EURCAD": 2.8, "EURAUD": 2.5, "EURNZD": 4.0, "AUDCAD": 2.5, "NZDCHF": 3.0,
        "AUDCHF": 2.5, "NZDCAD": 3.0}
COSTS = {s: p * 0.0001 for s, p in PIPS.items()}
raw = {s: load(s) for s in PIPS}
ix = raw["EURUSD"].index
for d in raw.values(): ix = ix.union(d.index)
data = {}
for s, d in raw.items():
    x = d.reindex(ix); x["close"] = x["close"].ffill()
    for k in ["open", "high", "low"]: x[k] = x[k].fillna(x["close"])
    data[s] = x
first = max(v["close"].first_valid_index() for v in data.values())
data = {s: v[v.index >= first].dropna() for s, v in data.items()}
idx = data["EURUSD"].index
for s in data: assert len(data[s]) == len(idx), s
I13, I20, I23 = (idx.searchsorted(pd.Timestamp(x)) for x in ["2013-01-01", "2020-01-01", "2023-01-01"])

FAMS = {"Asian fade": asian_fade, "Z-score fade": zscore_fade}
legs = {}
for f, fn in FAMS.items():
    for s in PIPS:
        tr = [t for t in simulate(data[s], fn(data[s]), COSTS[s]) if t["entry_i"] >= I13]
        for t in tr: t["gamba"] = f"{f} {s}"
        legs[(f, s)] = tr


def tstat(r):
    r = np.asarray(r); return float(r.mean() / (r.std(ddof=1) / math.sqrt(len(r)))) if len(r) > 2 and r.std() > 0 else 0.0


rows = []
for (f, s), tr in legs.items():
    R = lambda a, b: np.array([t["r"] for t in tr if a <= t["entry_i"] < b])
    a, v, te = R(I13, I20), R(I20, I23), R(I23, len(idx))
    sel = len(a) >= 15 and a.mean() > 0 and tstat(a) >= 1.0
    rows.append(dict(famiglia=f, simbolo=s, n_13_19=len(a), r_13_19=round(a.mean(), 3) if len(a) else None, t_13_19=round(tstat(a), 2),
                     n_20_22=len(v), r_20_22=round(v.mean(), 3) if len(v) else None, n_23_26=len(te),
                     r_23_26=round(te.mean(), 3) if len(te) else None, t_23_26=round(tstat(te), 2),
                     scelta=sel, confermata=bool(sel and len(v) > 0 and v.mean() > 0)))
L = pd.DataFrame(rows); L.to_csv("results/combo50_legs.csv", index=False)
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 100); pd.set_option("display.max_columns", 30)
print("=== GAMBE (36): scelta 2013-19, conferma 2020-22, test 2023-26 ===")
print(L.sort_values(["confermata", "t_13_19"], ascending=False).to_string(index=False))
keep = [(r.famiglia, r.simbolo) for r in L.itertuples() if r.confermata]
print("\nGambe tenute:", [f"{f} {s}" for f, s in keep])

PORTS = {"Attuale (2 gambe)": [("Asian fade", "EURCHF"), ("Z-score fade", "EURGBP")], f"Combinata ({len(keep)} gambe)": keep,
         "Tutte le 36 gambe (nessuna selezione)": list(legs)}


def port_trades(keys, a=I23, b=None):
    b = b or len(idx)
    return sorted([t for k in keys for t in legs[k] if a <= t["entry_i"] < b], key=lambda t: t["entry_i"])


def tm(r):
    r = np.asarray(r); w, l = r[r > 0], r[r <= 0]; s = mx = 0
    for x in r: s = s + 1 if x <= 0 else 0; mx = max(mx, s)
    t = tstat(r)
    return {"trade": len(r), "vincenti %": round(len(w) / len(r) * 100, 1), "R medio": round(r.mean(), 3), "profit factor": round(w.sum() / -l.sum(), 2),
            "max perdite di fila": mx, "t-stat": round(t, 2), "p-value": round(math.erfc(abs(t) / math.sqrt(2)), 4)}


months = pd.period_range(idx[I23], idx[-1], freq="M")
print("\n=== TEST 2023 - nov 2026: metriche per trade ===")
M = {}
for name, keys in PORTS.items():
    tr = port_trades(keys); m = tm([t["r"] for t in tr])
    pm = pd.Series([idx[t["entry_i"]].to_period("M") for t in tr]).value_counts().reindex(months, fill_value=0)
    m.update({"trade/mese medi": round(pm.mean(), 1), "mesi senza trade %": round((pm == 0).mean() * 100, 0)})
    # posizioni aperte contemporaneamente
    ev = sorted([(t["entry_i"], 1) for t in tr] + [(t["exit_i"], -1) for t in tr]); c = mx = 0
    for _, d in ev: c += d; mx = max(mx, c)
    m["max posizioni aperte insieme"] = mx
    M[name] = m
print(pd.DataFrame(M).to_string())

ENTRY = None
def run_window(tr_all, ent, s, days=60, base=0.10, winm=1.5, maxm=3.0, target=100.0, floor=20.0):
    e_new = idx.searchsorted(idx[s] + pd.Timedelta(days=days))
    sel = tr_all[np.searchsorted(ent, s):np.searchsorted(ent, e_new)]
    if not sel: return dict(finale=CAP, esito="nessun trade", trade=0, minimo=CAP)
    end = max(min(t["exit_i"], len(idx) - 1) for t in sel) + 1; Ln = end - s
    mult, heap, amounts = 1.0, [], []
    for t in sel:
        while heap and heap[0][0] < t["entry_i"]:
            _, r, _ = heapq.heappop(heap); mult = min(mult * winm, maxm) if r > 0 else 1.0
        amounts.append(CAP * base * mult); heapq.heappush(heap, (t["exit_i"], t["r"], id(t)))
    bal = np.zeros(Ln + 1); fl = np.zeros(Ln); flw = np.zeros(Ln)
    for t, A in zip(sel, amounts):
        a = t["entry_i"] - s; k = len(t["rc"])
        fl[a:a + k - 1] += A * t["rc"][:-1]; flw[a:a + k - 1] += A * t["rw"][:-1]; bal[a + k] += A * t["rc"][-1]
    b = np.cumsum(bal)[1:]; eq = CAP + b + fl; eqw = CAP + b + flw
    ht = np.flatnonzero(eq >= target); hf = np.flatnonzero(eqw <= floor)
    it = ht[0] if len(ht) else 10**9; jf = hf[0] if len(hf) else 10**9
    if it < jf: fin, es, cut = float(eq[it]), "obiettivo", it
    elif jf < 10**9: fin, es, cut = floor, "soglia", jf
    else: fin, es, cut = float(eq[-1]), "fine", Ln - 1
    return dict(finale=fin, esito=es, trade=int(sum(1 for t in sel if t["entry_i"] - s <= cut)), minimo=float(eqw[:cut + 1].min()))


def summary(res):
    f = res.finale
    return {"mediana EUR": round(f.median(), 1), "media EUR": round(f.mean(), 1), "10% peggiori": round(f.quantile(0.1), 1),
            "10% migliori": round(f.quantile(0.9), 1), "migliore": round(f.max(), 1), "peggiore": round(f.min(), 1),
            "raddoppio %": round((res.esito == "obiettivo").mean() * 100, 1), "scesa a 20 EUR %": round((res.esito == "soglia").mean() * 100, 1),
            "in guadagno %": round((f > CAP).mean() * 100, 1), "in perdita %": round((f < CAP).mean() * 100, 1),
            "sotto 40 EUR in qualche momento %": round((res.minimo < 40).mean() * 100, 1), "trade (mediana)": float(res.trade.median())}


week = idx.to_period("W").asi8; st = np.r_[0, np.flatnonzero(np.diff(week)) + 1]
st = st[(st >= I23) & (idx[st] <= idx[-1] - pd.Timedelta(days=80))]
print(f"\n=== TEST 2023 - nov 2026: conto 50 EUR, 60 giorni ({len(st)} partenze settimanali) ===")
S = {}
for name, keys in PORTS.items():
    tr = port_trades(keys); ent = np.array([t["entry_i"] for t in tr])
    for lab, kw in [("10% + anti-martingala", {}), ("5% + anti-martingala", dict(base=0.05)), ("2,5% + anti-martingala", dict(base=0.025))]:
        S[f"{name} | {lab}"] = summary(pd.DataFrame([run_window(tr, ent, s, **kw) for s in st]))
print(pd.DataFrame(S).T.to_string())
pd.DataFrame(S).T.to_csv("results/combo50_test.csv")
