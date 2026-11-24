"""Conto da 50 EUR aperto il 1 gennaio 2026 fino a oggi: Asian fade EURCHF + Z-score fade EURGBP (dati OANDA H1).
Rischio in % del capitale iniziale; anti-martingala opzionale (x1.5 dopo vincita, max x3, reset dopo perdita).
Freni come l'EA: obiettivo 100 EUR, soglia 20 EUR. Conto cent (nessun vincolo di lotto minimo)."""
import heapq, math
import numpy as np, pandas as pd
A = open("aggr50.py").read()
exec(A[:A.index("# ---------------------------------------------------------------- 1) quanti trade")])  # dati, trade, idx

START = pd.Timestamp("2026-01-01")
s0 = idx.searchsorted(START)
TR = [t for t in trades if t["entry_i"] >= s0]


def run(base, anti):
    mult, heap, rows = 1.0, [], []
    for t in TR:
        while heap and heap[0][0] < t["entry_i"]:
            _, r, _ = heapq.heappop(heap)
            if anti: mult = min(mult * 1.5, 3.0) if r > 0 else 1.0
        amt = CAP * base * mult
        rows.append(dict(t=t, amt=amt, mult=mult)); heapq.heappush(heap, (t["exit_i"], t["r"], id(t)))
    L = len(idx) - s0; bal = np.zeros(L + 1); fl = np.zeros(L); flw = np.zeros(L)
    for x in rows:
        t, Am = x["t"], x["amt"]; a = t["entry_i"] - s0; k = min(len(t["rc"]), L - a)
        if k == len(t["rc"]):
            fl[a:a + k - 1] += Am * t["rc"][:-1]; flw[a:a + k - 1] += Am * t["rw"][:-1]; bal[a + k] += Am * t["rc"][-1]
        else:
            fl[a:a + k] += Am * t["rc"][:k]; flw[a:a + k] += Am * t["rw"][:k]
    b = np.cumsum(bal)[1:]; eq = CAP + b + fl; eqw = CAP + b + flw
    stop = None
    ht = np.flatnonzero(eq >= 100); hf = np.flatnonzero(eqw <= 20)
    if len(ht) or len(hf):
        i = min(ht[0] if len(ht) else 10**9, hf[0] if len(hf) else 10**9); stop = idx[s0 + i]
        eq[i:] = eq[i]; eqw[i:] = eq[i]
    ser = pd.Series(eq, index=idx[s0:]); w = pd.Series(eqw, index=idx[s0:])
    pnl = [x["amt"] * x["t"]["r"] for x in rows if stop is None or idx[x["t"]["entry_i"]] < stop]
    pnl = np.array(pnl); wins = pnl[pnl > 0]; loss = pnl[pnl <= 0]
    peak = np.maximum.accumulate(ser.values); dd = (peak - w.values).max()
    mon = ser.groupby(ser.index.to_period("M")).last()
    mret = mon.diff().fillna(mon.iloc[0] - CAP)
    s = 0; mx = 0
    for p in pnl: s = s + 1 if p <= 0 else 0; mx = max(mx, s)
    met = {"capitale finale EUR": round(ser.iloc[-1], 2), "guadagno EUR": round(ser.iloc[-1] - CAP, 2),
           "rendimento %": round((ser.iloc[-1] / CAP - 1) * 100, 1), "massimo raggiunto EUR": round(ser.max(), 2),
           "minimo toccato EUR": round(w.min(), 2), "drawdown max EUR": round(dd, 2), "drawdown max %": round(dd / peak.max() * 100, 1),
           "trade": len(pnl), "vincenti": int((pnl > 0).sum()), "perdenti": int((pnl <= 0).sum()),
           "vincenti %": round((pnl > 0).mean() * 100, 1), "guadagno medio vincente EUR": round(wins.mean(), 2) if len(wins) else 0,
           "perdita media perdente EUR": round(loss.mean(), 2) if len(loss) else 0, "miglior trade EUR": round(pnl.max(), 2),
           "peggior trade EUR": round(pnl.min(), 2), "profit factor": round(wins.sum() / -loss.sum(), 2) if loss.sum() < 0 else None,
           "max perdite di fila": mx, "mesi positivi": f"{int((mret > 0).sum())} su {len(mret)}",
           "miglior mese EUR": round(mret.max(), 2), "peggior mese EUR": round(mret.min(), 2),
           "rischio max su un trade EUR": round(max(x["amt"] for x in rows), 2), "freno scattato": str(stop.date()) if stop is not None else "no"}
    return met, mon, mret, rows


pd.set_option("display.width", 250); pd.set_option("display.max_rows", 100)
print(f"Periodo: {idx[s0]} -> {idx[-1]}")
R, MON = {}, {}
for lab, base, anti in [("5% fisso", 0.05, False), ("5% + anti-martingala", 0.05, True), ("10% + anti-martingala (aggressivo)", 0.10, True)]:
    met, mon, mret, rows = run(base, anti); R[lab] = met; MON[lab] = mret.round(2)
    if lab == "5% fisso": ROWS = rows
print("\n=== METRICHE 1 gen 2026 - 24 nov 2026, partendo da 50 EUR ===\n" + pd.DataFrame(R).to_string())
eqm = pd.DataFrame(MON); eqm.index = eqm.index.astype(str)
print("\n=== Guadagno/perdita per mese (EUR) ===\n" + eqm.to_string())
print("\n=== Capitale a fine mese (EUR) ===\n" + (eqm.cumsum() + CAP).round(2).to_string())
print("\n=== I trade (importi con 5% fisso = 2,50 EUR di rischio) ===")
tl = pd.DataFrame([dict(strategia=x["t"]["strategia"], entrata=idx[x["t"]["entry_i"]].strftime("%d/%m %H:%M"),
                        uscita=idx[min(x["t"]["exit_i"], len(idx) - 1)].strftime("%d/%m %H:%M"),
                        direzione="long" if x["t"]["d"] > 0 else "short", R=round(x["t"]["r"], 2), EUR=round(x["amt"] * x["t"]["r"], 2)) for x in ROWS])
print(tl.to_string(index=False)); tl.to_csv("results/jan2026_trades.csv", index=False)
pd.DataFrame(R).to_csv("results/jan2026_metrics.csv")
