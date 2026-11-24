"""Ricerca di nuove strategie su dati GIORNALIERI OANDA (indici, materie prime, obbligazioni), 2003 - nov 2026.
Protocollo: SCELTA 2013-2019 (n>=15, R>0, t>=1), CONFERMA 2020-2022 (R>0), TEST 2023 - nov 2026.
Costi: spread in % del prezzo per classe + finanziamento overnight CFD 5% annuo sul nozionale (long e short)."""
import glob, math
import numpy as np, pandas as pd

IDX = ["SPX500", "NAS100", "US30", "US2000", "DE30", "UK100", "FR40", "EU50", "JP225", "AU200", "HK33", "CH20", "ESP35", "NL25", "CN50"]
MET = ["XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD", "XCUUSD"]; ENE = ["WTI", "BRENT", "NATGAS"]; AGR = ["CORN", "WHEAT", "SOYBN", "SUGAR"]
BND = ["UST2", "UST5", "UST10", "UST30", "BUND", "GILT"]
ALL = IDX + MET + ENE + AGR + BND
SPREAD = {**{s: 0.0002 for s in IDX}, **{s: 0.0004 for s in MET}, **{s: 0.0006 for s in ENE}, **{s: 0.0012 for s in AGR}, **{s: 0.0003 for s in BND}}
FIN = 0.05 / 365   # per giorno di calendario


def load(s):
    d = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(f"data/daily/{s}_*.parquet"))])
    d["Date"] = (pd.to_datetime(d.time, unit="s") + pd.Timedelta(hours=2)).dt.normalize()
    d = d.drop_duplicates("Date").set_index("Date").sort_index()[["open", "high", "low", "close"]]
    return d[d.index.dayofweek < 5]


def atr(d, n):
    pc = d.close.shift()
    tr = pd.concat([d.high - d.low, (d.high - pc).abs(), (d.low - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def rsi(c, n):
    x = c.diff(); up = x.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean(); dn = (-x.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn)


def spec0(n):
    return dict(sig=np.zeros(n, int), stop=np.full(n, np.nan), tp=np.full(n, np.nan), exl=np.zeros(n, bool), exs=np.zeros(n, bool),
                trl=None, trs=None, maxb=10**9)


def tsmom(d):          # momentum 12 mesi, ribilanciato il primo giorno di ogni mese
    n = len(d); sp = spec0(n); c = d.close; a = atr(d, 20)
    first = np.r_[True, d.index.month[1:] != d.index.month[:-1]]
    ret = c / c.shift(252) - 1
    last_of_prev = np.r_[first[1:], False]            # ultima barra del mese -> ingresso il primo giorno del mese dopo
    sig = np.where(last_of_prev & (ret > 0), 1, np.where(last_of_prev & (ret < 0), -1, 0))
    sp["sig"] = sig; sp["stop"] = (3 * a).to_numpy()
    sp["exl"] = last_of_prev.copy(); sp["exs"] = last_of_prev.copy()
    return sp


def donchian(d, nin=50, nout=20):
    n = len(d); sp = spec0(n); a = atr(d, 20)
    up = d.high.rolling(nin).max().shift(); dn = d.low.rolling(nin).min().shift()
    sp["sig"] = np.where(d.close > up, 1, np.where(d.close < dn, -1, 0)); sp["stop"] = (2 * a).to_numpy()
    sp["trl"] = d.low.rolling(nout).min().to_numpy(); sp["trs"] = d.high.rolling(nout).max().to_numpy()
    return sp


def rsi2(d):
    n = len(d); sp = spec0(n); c = d.close; r = rsi(c, 2); a = atr(d, 14)
    sp["sig"] = np.where((c > c.rolling(200).mean()) & (r < 10), 1, 0); sp["stop"] = (3 * a).to_numpy()
    sp["exl"] = (c > c.rolling(5).mean()).to_numpy(); sp["maxb"] = 10
    return sp


def tom(d):
    n = len(d); sp = spec0(n); a = atr(d, 14)
    ym = d.index.year * 12 + d.index.month
    g = pd.Series(ym, index=d.index).groupby(ym)
    rank_end = (g.cumcount(ascending=False) + 1).to_numpy(); rank_start = (g.cumcount() + 1).to_numpy()
    sp["sig"] = np.where(rank_end == 2, 1, 0); sp["stop"] = (3 * a).to_numpy()
    sp["exl"] = rank_start == 3; sp["maxb"] = 7
    return sp


def sma200(d):
    n = len(d); sp = spec0(n); c = d.close; m = c.rolling(200).mean(); a = atr(d, 20)
    above = (c > m).to_numpy(); cross = above & ~np.r_[False, above[:-1]]
    sp["sig"] = np.where(cross, 1, 0); sp["stop"] = (5 * a).to_numpy(); sp["exl"] = ~above
    return sp


def prevday(d):
    n = len(d); sp = spec0(n); a = atr(d, 14)
    # rottura del massimo/minimo di ieri sulla chiusura di oggi -> ingresso domani, uscita dopo 1 giorno
    sp["sig"] = np.where(d.close > d.high.shift(), 1, np.where(d.close < d.low.shift(), -1, 0)); sp["stop"] = (1 * a).to_numpy()
    sp["maxb"] = 1
    return sp


FAMILIES = {"Momentum 12 mesi": (tsmom, ALL), "Donchian 50/20": (donchian, ALL), "RSI2 dip-buy": (rsi2, IDX),
            "Turn of month": (tom, IDX), "Trend SMA200": (sma200, IDX), "Breakout giorno prec.": (prevday, MET + ENE)}


def simulate(d, sp, spread):
    o, h, l, c = (d[k].to_numpy() for k in ["open", "high", "low", "close"]); dates = d.index; n = len(d); out = []; i = 0
    while i < n - 2:
        dr = sp["sig"][i]
        if dr == 0 or not np.isfinite(sp["stop"][i]) or sp["stop"][i] <= 0: i += 1; continue
        e = i + 1; entry = o[e]; stop = entry - dr * sp["stop"][i]; cost = entry * spread; risk = sp["stop"][i] + cost
        rc, rw = [], []; j = e
        while True:
            days = (dates[j] - dates[e]).days + 1; fin = entry * FIN * days
            px = None
            if dr == 1:
                if o[j] <= stop and j > e: px = o[j]
                elif l[j] <= stop: px = stop
                worst = l[j]
            else:
                if o[j] >= stop and j > e: px = o[j]
                elif h[j] >= stop: px = stop
                worst = h[j]
            if px is not None:
                rr = (dr * (px - entry) - cost - fin) / risk; rc.append(rr); rw.append(rr); break
            rc.append((dr * (c[j] - entry) - cost - fin) / risk); rw.append((dr * (worst - entry) - cost - fin) / risk)
            if j == n - 2 or (dr == 1 and sp["exl"][j]) or (dr == -1 and sp["exs"][j]) or (j - e + 1) >= sp["maxb"]:
                j += 1; rr = (dr * (o[j] - entry) - cost - fin) / risk; rc.append(rr); rw.append(rr); break
            if dr == 1 and sp["trl"] is not None and np.isfinite(sp["trl"][j]): stop = max(stop, sp["trl"][j])
            if dr == -1 and sp["trs"] is not None and np.isfinite(sp["trs"][j]): stop = min(stop, sp["trs"][j])
            j += 1
        out.append(dict(entry=dates[e], exit=dates[min(j, n - 1)], d=dr, r=rc[-1], rc=np.array(rc), rw=np.array(rw)))
        i = j
    return out


def tstat(r):
    r = np.asarray(r); return float(r.mean() / (r.std(ddof=1) / math.sqrt(len(r)))) if len(r) > 2 and r.std() > 0 else 0.0


if __name__ == "__main__":
    data = {s: load(s) for s in ALL}
    P = {"13-19": ("2013-01-01", "2020-01-01"), "20-22": ("2020-01-01", "2023-01-01"), "23-26": ("2023-01-01", "2027-01-01")}
    rows, alltr = [], {}
    for f, (fn, syms) in FAMILIES.items():
        for s in syms:
            tr = simulate(data[s], fn(data[s]), SPREAD[s]); alltr[(f, s)] = tr
            row = dict(famiglia=f, simbolo=s)
            for p, (a, b) in P.items():
                r = np.array([t["r"] for t in tr if pd.Timestamp(a) <= t["entry"] < pd.Timestamp(b)])
                row[f"n_{p}"] = len(r); row[f"r_{p}"] = round(r.mean(), 3) if len(r) else np.nan; row[f"t_{p}"] = round(tstat(r), 2) if len(r) > 2 else np.nan
            row["scelta"] = row["n_13-19"] >= 15 and row["r_13-19"] > 0 and row["t_13-19"] >= 1
            row["confermata"] = bool(row["scelta"] and row["n_20-22"] > 0 and row["r_20-22"] > 0)
            rows.append(row)
    L = pd.DataFrame(rows); L.to_csv("results/daily_legs.csv", index=False)
    import pickle; pickle.dump(alltr, open("/tmp/claude-0/daily_trades.pkl", "wb"))
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 200); pd.set_option("display.max_columns", 30)
    fam = []
    for f in FAMILIES:
        g = {}
        for p, (a, b) in P.items():
            r = np.array([t["r"] for (ff, s), tr in alltr.items() if ff == f for t in tr if pd.Timestamp(a) <= t["entry"] < pd.Timestamp(b)])
            g[f"n_{p}"] = len(r); g[f"r_{p}"] = round(r.mean(), 3); g[f"t_{p}"] = round(tstat(r), 2)
        fam.append(dict(famiglia=f, **g))
    print("=== FAMIGLIE INTERE (tutti gli strumenti, nessuna selezione) ===\n" + pd.DataFrame(fam).to_string(index=False))
    print("\n=== GAMBE SCELTE 2013-19 ===\n" + L[L.scelta].sort_values("t_13-19", ascending=False).to_string(index=False))
