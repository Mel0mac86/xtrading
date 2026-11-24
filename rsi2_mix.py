"""Varianti di combinazione RSI2 indici + forex: rischio diverso per famiglia e tetto alle posizioni sugli indici.
Conto 100 EUR, P/L alla chiusura. Periodi: 2013-2019, 2020-2022, 2023 - nov 2026 e 2026."""
import numpy as np, pandas as pd
src = open("rsi2_portfolio.py").read()
exec(src[:src.index('print("=== RSI2 per indice')])


def account(rsi_risk, fx_risk, rsi_max, start, end, cap=100.0):
    taken, open_idx = [], []
    for t in sorted(rsi_tr + fx_tr, key=lambda t: t["entry"]):
        if not (pd.Timestamp(start) <= t["entry"] < pd.Timestamp(end)): continue
        if t["strategia"] == "RSI2 indici":
            open_idx = [e for e in open_idx if e > t["entry"]]
            if rsi_max and len(open_idx) >= rsi_max: continue
            open_idx.append(t["exit"]); taken.append((t, rsi_risk))
        else:
            taken.append((t, fx_risk))
    pnl = pd.Series([cap * rk * t["r"] for t, rk in taken], index=[t["exit"] for t, _ in taken]).groupby(level=0).sum().sort_index()
    days = pd.bdate_range(start, min(pd.Timestamp(end), pd.Timestamp("2026-11-24")))
    eq = cap + pnl.reindex(days, fill_value=0).cumsum(); peak = eq.cummax()
    mon = eq.groupby(eq.index.to_period("M")).last(); mret = mon.diff().fillna(mon.iloc[0] - cap)
    yrs = len(days) / 252
    return {"rend. annuo %": round((eq.iloc[-1] - cap) / cap * 100 / yrs, 1), "drawdown max %": round(((peak - eq) / peak).max() * 100, 1),
            "rapporto rend/DD": round((eq.iloc[-1] - cap) / cap / yrs / max(((peak - eq) / peak).max(), 1e-9), 2),
            "mesi positivi %": round((mret > 0).mean() * 100), "peggior mese %": round(mret.min() / cap * 100, 1), "trade/mese": round(len(taken) / len(mret), 1)}


VAR = {"Solo forex 2%": (0, 0.02, None), "Solo RSI2 2%, max 6": (0.02, 0, 6), "Forex 2% + RSI2 2%, max 6": (0.02, 0.02, 6),
       "Forex 2% + RSI2 1%, max 3": (0.01, 0.02, 3), "Forex 2% + RSI2 1%, max 2": (0.01, 0.02, 2), "Forex 2% + RSI2 0,5%, nessun tetto": (0.005, 0.02, None),
       "Forex 3% + RSI2 1%, max 3": (0.01, 0.03, 3)}
PER = {"2013-19": ("2013-01-01", "2020-01-01"), "2020-22": ("2020-01-01", "2023-01-01"), "2023-26": ("2023-01-01", "2027-01-01"), "2026": ("2026-01-01", "2027-01-01")}
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
for p, (a, b) in PER.items():
    print(f"\n=== {p} ===")
    print(pd.DataFrame({k: account(*v, a, b) for k, v in VAR.items()}).T.to_string())
