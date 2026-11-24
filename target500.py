"""Probabilita' di arrivare a 500 EUR in 30 giorni partendo da 50 o 100 EUR, con i trade reali
(Asian fade EURCHF + Z-score EURGBP + RSI2 su 15 indici), rischio = % del capitale ATTUALE a ogni trade
(interesse composto), finestre di 30 giorni con partenza ogni settimana 2013 - ott 2026.
Semplificazione: P/L contabilizzato alla chiusura, in ordine di chiusura; conto azzerato se scende sotto 1 EUR."""
import numpy as np, pandas as pd
src = open("rsi2_portfolio.py").read()
exec(src[:src.index('print("=== RSI2 per indice')])
TR = sorted(rsi_tr + fx_tr, key=lambda t: t["exit"])
EX = np.array([t["exit"] for t in TR], dtype="datetime64[ns]"); EN = np.array([t["entry"] for t in TR], dtype="datetime64[ns]")
R = np.array([t["r"] for t in TR])
starts = pd.date_range("2013-01-07", "2026-10-19", freq="W-MON")


def run(cap, risk, days=30, target=500.0):
    out = []
    for s in starts:
        e = s + pd.Timedelta(days=days)
        m = (EN >= np.datetime64(s)) & (EX < np.datetime64(e))
        eq = cap; mx = cap
        for r in R[m]:
            eq = eq * (1 + risk * r); mx = max(mx, eq)
            if eq >= target or eq < 1: break
        out.append((eq, mx))
    f = np.array([o[0] for o in out]); top = np.array([o[1] for o in out])
    return {"arriva a 500 EUR %": round((top >= target).mean() * 100, 2), "perde tutto (<1 EUR) %": round((f < 1).mean() * 100, 1),
            "perde piu' di meta' %": round((f < cap / 2).mean() * 100, 1), "risultato tipico EUR": round(np.median(f), 1),
            "miglior risultato EUR": round(f.max(), 1), "trade nei 30 gg (mediana)": int(np.median([((EN >= np.datetime64(s)) & (EX < np.datetime64(s + pd.Timedelta(days=30)))).sum() for s in starts[::10]]))}


pd.set_option("display.width", 250)
for cap in [50, 100]:
    rows = {f"rischio {int(r*100)}% del conto a trade": run(cap, r) for r in [0.05, 0.10, 0.25, 0.50, 1.00]}
    print(f"\n=== Partenza {cap} EUR, obiettivo 500 EUR in 30 giorni ({len(starts)} finestre) ===")
    print(pd.DataFrame(rows).T.to_string())
