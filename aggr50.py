"""Profilo aggressivo con 50 EUR: Asian fade EURCHF + Z-score fade EURGBP (dati OANDA H1 2013 - nov 2026).
Rischio base 10% del capitale iniziale, anti-martingala (x1.5 dopo vincita, max x3, reset dopo perdita),
obiettivo 100 EUR, soglia 20 EUR (-60%), 60 giorni. Conto cent (nessun vincolo di lotto minimo)."""
import glob, math, heapq
import numpy as np, pandas as pd

CAP, BASE, WINM, MAXM, TARGET, FLOOR, DAYS = 50.0, 0.10, 1.5, 3.0, 100.0, 20.0, 60
COST = {"EURCHF": 0.00022, "EURGBP": 0.00018}


def load(sym):
    d = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(f"data/oanda/OANDA_{sym}_*_60_*.parquet"))])
    d["Date"] = pd.to_datetime(d.time, unit="s", utc=True).dt.tz_convert("Europe/Helsinki").dt.tz_localize(None)
    d = d.drop_duplicates("Date").set_index("Date").sort_index()[["open", "high", "low", "close"]]
    return d[d.index.dayofweek < 5]


def atr(df, n):
    pc = df["close"].shift()
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def empty(n):
    return dict(sig=np.zeros(n, int), stop_dist=np.full(n, np.nan), tp_dist=np.full(n, np.nan),
                exit_long=np.zeros(n, bool), exit_short=np.zeros(n, bool))


def asian_fade(df, k=2.5, n_bb=20, stop_atr=1.5):
    n = len(df); c = df["close"]; m = c.rolling(n_bb).mean(); sd = c.rolling(n_bb).std()
    hr = df.index.hour.to_numpy(); a = atr(df, 14); sess = (hr >= 0) & (hr < 8)
    sp = empty(n)
    sp["sig"] = np.where(sess & (c < m - k * sd), 1, np.where(sess & (c > m + k * sd), -1, 0))
    sp["stop_dist"] = (stop_atr * 4 * a).to_numpy()
    sp["exit_long"] = (c >= m).to_numpy() | (hr >= 10); sp["exit_short"] = (c <= m).to_numpy() | (hr >= 10)
    return sp


def zscore_fade(df, n=50, z_in=1.5, atr_mult=2.0, max_days=15):
    N = len(df); key = df.index.normalize(); g = df.groupby(key)
    d = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(), "close": g["close"].last()})
    pos = pd.Series(np.arange(N), index=df.index).groupby(key).last().to_numpy()
    z = (d["close"] - d["close"].rolling(n).mean()) / d["close"].rolling(n).std(); a = atr(d, 14)
    def h1(v):
        o = np.full(N, np.nan); o[pos] = np.asarray(v, float); return o
    sp = empty(N)
    sp["sig"] = np.nan_to_num(h1(np.where(z < -z_in, 1, np.where(z > z_in, -1, 0)))).astype(int)
    sp["stop_dist"] = h1(atr_mult * a)
    sp["exit_long"] = h1(z > 0) == 1; sp["exit_short"] = h1(z < 0) == 1
    sp["max_bars"] = max_days * 24
    return sp


def simulate(df, spec, cost):
    o, h, l, c = (df[k].to_numpy() for k in ["open", "high", "low", "close"]); n = len(df)
    sig, sd, exl, exs, mb = spec["sig"], spec["stop_dist"], spec["exit_long"], spec["exit_short"], spec.get("max_bars", 10**9)
    out, i = [], 0
    while i < n - 1:
        d = sig[i]
        if d == 0 or not np.isfinite(sd[i]) or sd[i] <= 0: i += 1; continue
        e = i + 1; entry = o[e]; stop = entry - d * sd[i]; risk = sd[i] + cost
        rc, rw = [], []; j = e
        while True:
            worst = l[j] if d == 1 else h[j]; px = None
            if d == 1:
                if o[j] <= stop and j > e: px = o[j]
                elif l[j] <= stop: px = stop
            else:
                if o[j] >= stop and j > e: px = o[j]
                elif h[j] >= stop: px = stop
            if px is not None:
                rr = (d * (px - entry) - cost) / risk; rc.append(rr); rw.append(rr); break
            rc.append((d * (c[j] - entry) - cost) / risk); rw.append((d * (worst - entry) - cost) / risk)
            if j == n - 2 or (d == 1 and exl[j]) or (d == -1 and exs[j]) or (j - e + 1) >= mb:
                j += 1; rr = (d * (o[j] - entry) - cost) / risk; rc.append(rr); rw.append(rr); break
            j += 1
        out.append(dict(entry_i=e, exit_i=j, d=d, rc=np.array(rc), rw=np.array(rw), r=rc[-1]))
        i = j
    return out


# ---------------------------------------------------------------- dati e trade
raw = {s: load(s) for s in COST}
ix = raw["EURCHF"].index.union(raw["EURGBP"].index)
data = {}
for s, d in raw.items():
    x = d.reindex(ix); x["close"] = x["close"].ffill()
    for k in ["open", "high", "low"]: x[k] = x[k].fillna(x["close"])
    data[s] = x.dropna()
first = max(v.index[0] for v in data.values()); data = {s: v[v.index >= first] for s, v in data.items()}
idx = data["EURCHF"].index
T0 = idx.searchsorted(pd.Timestamp("2013-01-01"))
trades = []
for name, s, fn in [("Asian fade EURCHF", "EURCHF", asian_fade), ("Z-score fade EURGBP", "EURGBP", zscore_fade)]:
    for t in simulate(data[s], fn(data[s]), COST[s]):
        if t["entry_i"] >= T0: t["strategia"] = name; trades.append(t)
trades.sort(key=lambda t: t["entry_i"])
tdf = pd.DataFrame([dict(strategia=t["strategia"], entrata=idx[t["entry_i"]], uscita=idx[min(t["exit_i"], len(idx) - 1)],
                         direzione="long" if t["d"] > 0 else "short", r=t["r"], ore=t["exit_i"] - t["entry_i"]) for t in trades])
tdf.to_csv("results/aggr50_trades.csv", index=False)
months = pd.period_range(idx[T0], idx[-1], freq="M")
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)

# ---------------------------------------------------------------- 1) quanti trade
print(f"Periodo: {idx[T0].date()} - {idx[-1].date()} ({len(months)} mesi)")
per_m = tdf.groupby([tdf.entrata.dt.to_period("M"), "strategia"]).size().unstack(fill_value=0).reindex(months, fill_value=0)
per_m["totale"] = per_m.sum(axis=1)
print("\n=== 1) TRADE AL MESE ===")
print(per_m.describe().loc[["mean", "50%", "min", "max"]].rename(index={"mean": "media", "50%": "mediana"}).round(2).to_string())
print("mesi con 0 trade:", int((per_m.totale == 0).sum()), "su", len(per_m), f"({(per_m.totale == 0).mean()*100:.0f}%)")
print("distribuzione trade/mese:", per_m.totale.value_counts().sort_index().to_dict())
yearly = tdf.groupby([tdf.entrata.dt.year, "strategia"]).size().unstack(fill_value=0); yearly["totale"] = yearly.sum(axis=1)
print("\nTrade per anno:\n" + yearly.to_string())


# ---------------------------------------------------------------- 2) metriche per trade
def tm(r, hours):
    r = np.asarray(r); w, l = r[r > 0], r[r <= 0]; s = mx = 0
    for x in r: s = s + 1 if x <= 0 else 0; mx = max(mx, s)
    t = r.mean() / (r.std(ddof=1) / math.sqrt(len(r)))
    return {"trade": len(r), "vincenti %": round(len(w) / len(r) * 100, 1), "R medio": round(r.mean(), 3),
            "vincita media R": round(w.mean(), 3), "perdita media R": round(l.mean(), 3), "miglior R": round(r.max(), 2),
            "peggior R": round(r.min(), 2), "profit factor": round(w.sum() / -l.sum(), 2), "max perdite di fila": mx,
            "durata media ore": round(float(np.mean(hours)), 1), "t-stat": round(t, 2), "p-value": round(math.erfc(abs(t) / math.sqrt(2)), 4)}
mt = {n: tm(g.r, g.ore) for n, g in tdf.groupby("strategia")}; mt["TOTALE"] = tm(tdf.r, tdf.ore)
print("\n=== 2) METRICHE PER TRADE (R = multipli del rischio del trade) ===\n" + pd.DataFrame(mt).to_string())


# ---------------------------------------------------------------- 3) conto da 50 EUR, profilo aggressivo
ENT = np.array([t["entry_i"] for t in trades])
day_id = pd.factorize(idx.normalize())[0]


def run_window(s, days=DAYS, base=BASE, winm=WINM, maxm=MAXM, target=TARGET, floor=FLOOR):
    e_new = idx.searchsorted(idx[s] + pd.Timedelta(days=days))
    sel = [t for t in trades[np.searchsorted(ENT, s):np.searchsorted(ENT, e_new)]]
    if not sel: return dict(finale=CAP, esito="nessun trade", trade=0, minimo=CAP, massimo=CAP, mult_max=1.0)
    end = max(min(t["exit_i"], len(idx) - 1) for t in sel) + 1; L = end - s
    mult, heap, amounts = 1.0, [], []
    for t in sel:
        while heap and heap[0][0] < t["entry_i"]:
            _, r = heapq.heappop(heap)[:2]; mult = min(mult * winm, maxm) if r > 0 else 1.0
        amounts.append(CAP * base * mult); heapq.heappush(heap, (t["exit_i"], t["r"], id(t)))
    mult_max = max(amounts) / (CAP * base)
    bal = np.zeros(L + 1); fl = np.zeros(L); flw = np.zeros(L)
    for t, A in zip(sel, amounts):
        a = t["entry_i"] - s; k = len(t["rc"])
        fl[a:a + k - 1] += A * t["rc"][:-1]; flw[a:a + k - 1] += A * t["rw"][:-1]; bal[a + k] += A * t["rc"][-1]
    b = np.cumsum(bal)[1:]; eq = CAP + b + fl; eqw = CAP + b + flw
    hit_t = np.flatnonzero(eq >= target); hit_f = np.flatnonzero(eqw <= floor)
    it = hit_t[0] if len(hit_t) else 10**9; jf = hit_f[0] if len(hit_f) else 10**9
    if it < jf: fin, es, cut = float(eq[it]), "obiettivo", it
    elif jf < 10**9: fin, es, cut = floor, "soglia", jf
    else: fin, es, cut = float(eq[-1]), "fine periodo", L - 1
    ntr = int(sum(1 for t in sel if t["entry_i"] - s <= cut))
    return dict(finale=fin, esito=es, trade=ntr, minimo=float(eqw[:cut + 1].min()), massimo=float(eq[:cut + 1].max()), mult_max=mult_max)


week = idx.to_period("W").asi8; st = np.r_[0, np.flatnonzero(np.diff(week)) + 1]
st = st[(st >= T0) & (idx[st] <= idx[-1] - pd.Timedelta(days=DAYS + 20))]


def summary(res):
    f = res.finale
    return {"finestre": len(res), "risultato mediano EUR": round(f.median(), 1), "media EUR": round(f.mean(), 1),
            "10% peggiori EUR": round(f.quantile(0.1), 1), "25% EUR": round(f.quantile(0.25), 1), "75% EUR": round(f.quantile(0.75), 1),
            "10% migliori EUR": round(f.quantile(0.9), 1), "migliore EUR": round(f.max(), 1), "peggiore EUR": round(f.min(), 1),
            "obiettivo 100 EUR %": round((res.esito == "obiettivo").mean() * 100, 1), "soglia 20 EUR %": round((res.esito == "soglia").mean() * 100, 1),
            "in guadagno %": round((f > CAP).mean() * 100, 1), "in perdita %": round((f < CAP).mean() * 100, 1),
            "sotto 40 EUR in qualche momento %": round((res.minimo < 40).mean() * 100, 1),
            "trade per finestra (mediana)": float(res.trade.median()), "moltiplicatore max raggiunto (mediana)": round(float(res.mult_max.median()), 2)}

res = pd.DataFrame([dict(partenza=idx[s], **run_window(s)) for s in st]); res.to_csv("results/aggr50_windows.csv", index=False)
print("\n=== 3) CONTO 50 EUR, AGGRESSIVO, 60 GIORNI (partenza ogni settimana) ===")
s3 = {"aggressivo (10%, anti-martingala)": summary(res)}
for lab, kw in [("10% fisso, senza anti-martingala", dict(maxm=1.0)), ("5% fisso", dict(base=0.05, maxm=1.0)),
                ("aggressivo, 30 giorni", dict(days=30))]:
    s3[lab] = summary(pd.DataFrame([run_window(s, **kw) for s in st]))
print(pd.DataFrame(s3).to_string())
print("\nPer anno di partenza (aggressivo, 60 gg):")
print(res.assign(anno=res.partenza.dt.year).groupby("anno").apply(lambda g: pd.Series({
    "finestre": len(g), "mediana EUR": round(g.finale.median(), 1), "obiettivo %": round((g.esito == "obiettivo").mean() * 100, 0),
    "soglia %": round((g.esito == "soglia").mean() * 100, 0), "in perdita %": round((g.finale < CAP).mean() * 100, 0)}), include_groups=False).to_string())
