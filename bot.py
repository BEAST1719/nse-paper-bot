"""NSE paper-trading bot (free). Usage:  python bot.py backtest   |   python bot.py paper
Strategy: trend breakout. Buy when close > 20-day high AND close > 50-day average.
Sell when close < 10-day low OR price falls 7% below entry. Max 10 positions, equal size.
Orders are decided at the close and filled at the NEXT day's open (no peeking at the future).
EDUCATIONAL ONLY. Not investment advice. No strategy is guaranteed profitable."""
import json, sys
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

START_CASH = 1_000_000      # Rs 10 lakh of FAKE money
MAX_POS = 10
STOP = 0.07
COST = 0.0012               # ~brokerage+STT+charges per side (rough)
SLIP = 0.0005               # slippage per side
BENCH = "^NSEI"
STATE, TRADES, REPORT = Path("state.json"), Path("trades.csv"), Path("report.md")

DEFAULT = """RELIANCE TCS HDFCBANK ICICIBANK INFY BHARTIARTL ITC SBIN LT HINDUNILVR KOTAKBANK AXISBANK
BAJFINANCE MARUTI SUNPHARMA M&M NTPC ONGC POWERGRID TITAN ULTRACEMCO ASIANPAINT COALINDIA WIPRO
HCLTECH TECHM NESTLEIND JSWSTEEL TATASTEEL ADANIENT ADANIPORTS BAJAJFINSV GRASIM CIPLA DRREDDY
EICHERMOT HEROMOTOCO HINDALCO INDUSINDBK BPCL BRITANNIA APOLLOHOSP DIVISLAB TATACONSUM SBILIFE
HDFCLIFE BAJAJ-AUTO SHRIRAMFIN TRENT BEL ETERNAL DMART PIDILITIND HAL IRCTC VEDL GAIL DLF PNB
BANKBARODA CANBK TATAPOWER JIOFIN LICI""".split()

def universe():
    f = Path("universe.txt")   # optional: put your own symbols here, one per line
    syms = [s.strip() for s in f.read_text().split() if s.strip()] if f.exists() else DEFAULT
    return [s + ".NS" for s in syms]

def prep(df):
    df = df.dropna(subset=["Close"]).copy()
    df["sma50"] = df.Close.rolling(50).mean()
    df["hi20"] = df.High.rolling(20).max().shift(1)
    df["lo10"] = df.Low.rolling(10).min().shift(1)
    df["mom"] = df.Close.pct_change(60)
    df["entry"] = (df.Close > df.hi20) & (df.Close > df.sma50)
    return df

def download(period):
    syms = universe()
    raw = yf.download(syms + [BENCH], period=period, auto_adjust=True,
                      group_by="ticker", progress=False, threads=True)
    data = {}
    for s in syms:
        try:
            d = raw[s].dropna(how="all")
            if len(d) > 80:
                data[s] = prep(d)
            else:
                print("skipped (no data):", s)
        except Exception:
            print("skipped:", s)
    bench = raw[BENCH]["Close"].dropna()
    return data, bench

def new_state():
    return {"cash": START_CASH, "positions": {}, "pending": [], "equity": [], "last_date": None, "trades": []}

def step(st, date, rows):
    """One trading day. rows = {symbol: that day's bar}."""
    cash, pos = st["cash"], st["positions"]
    # 1) fill yesterday's orders at today's open (sells first, to free cash)
    keep = []
    for o in sorted(st["pending"], key=lambda o: o["side"] != "SELL"):
        r = rows.get(o["sym"])
        if r is None:
            keep.append(o); continue
        if o["side"] == "SELL" and o["sym"] in pos:
            p = pos.pop(o["sym"]); px = r.Open * (1 - SLIP)
            cash += p["qty"] * px * (1 - COST)
            st["trades"].append({"sym": o["sym"], "entry_date": p["date"], "exit_date": date,
                "entry": round(p["entry"], 2), "exit": round(px, 2), "qty": p["qty"],
                "pnl_pct": round((px * (1 - COST) / (p["entry"] * (1 + COST)) - 1) * 100, 2)})
        elif o["side"] == "BUY" and o["sym"] not in pos:
            px = r.Open * (1 + SLIP)
            qty = int(min(o["alloc"], cash) / (px * (1 + COST)))
            if qty > 0:
                cash -= qty * px * (1 + COST)
                pos[o["sym"]] = {"qty": qty, "entry": px, "stop": px * (1 - STOP), "date": date}
    st["pending"] = keep
    # 2) mark-to-market at today's close
    eq = cash + sum(p["qty"] * (rows[s].Close if s in rows else p["entry"]) for s, p in pos.items())
    # 3) decide exits and entries for tomorrow
    queued = {o["sym"] for o in st["pending"]}
    for s, p in pos.items():
        r = rows.get(s)
        if r is not None and s not in queued and (r.Close < r.lo10 or r.Close < p["stop"]):
            st["pending"].append({"sym": s, "side": "SELL"}); queued.add(s)
    slots = MAX_POS - len(pos) - sum(o["side"] == "BUY" for o in st["pending"])
    cands = sorted(((r.mom, s) for s, r in rows.items()
                    if r.entry and s not in pos and s not in queued and not np.isnan(r.mom)), reverse=True)
    for _, s in cands[:max(slots, 0)]:
        st["pending"].append({"sym": s, "side": "BUY", "alloc": eq / MAX_POS})
    st["cash"], st["last_date"] = cash, date
    st["equity"].append([date, round(eq, 2)])

def rows_for(data, date):
    ts = pd.Timestamp(date)
    return {s: d.loc[ts] for s, d in data.items() if ts in d.index}

def stats(st, bench):
    eq = pd.Series({pd.Timestamp(d): v for d, v in st["equity"]})
    yrs = max(len(eq) / 252, 1e-9)
    tot = eq.iloc[-1] / eq.iloc[0] - 1
    cagr = (1 + tot) ** (1 / yrs) - 1
    dd = (eq / eq.cummax() - 1).min()
    t = pd.DataFrame(st["trades"])
    b = bench.reindex(eq.index).ffill()
    btot = b.iloc[-1] / b.iloc[0] - 1
    out = [f"Days simulated : {len(eq)} (~{yrs:.1f} yrs)",
           f"Strategy return: {tot*100:.1f}%   CAGR {cagr*100:.1f}%   Max drawdown {dd*100:.1f}%",
           f"Nifty50 buy&hold: {btot*100:.1f}%   (the bar your bot must beat)"]
    if len(t):
        out.append(f"Trades: {len(t)}   Win rate {((t.pnl_pct>0).mean())*100:.0f}%   Avg trade {t.pnl_pct.mean():.2f}%")
    return "\n".join(out)

def backtest(data, bench):
    st = new_state()
    for date in bench.index[60:]:
        step(st, str(date.date()), rows_for(data, date))
    print(stats(st, bench))
    pd.DataFrame(st["trades"]).to_csv("backtest_trades.csv", index=False)
    pd.DataFrame(st["equity"], columns=["date", "equity"]).to_csv("backtest_equity.csv", index=False)

def paper(data, bench):
    st = json.loads(STATE.read_text()) if STATE.exists() else new_state()
    date = str(bench.index[-1].date())
    if st["last_date"] == date:
        print("Already processed", date, "- market closed/holiday?"); return
    step(st, date, rows_for(data, date))
    STATE.write_text(json.dumps(st, indent=1))
    pd.DataFrame(st["trades"]).to_csv(TRADES, index=False)
    lines = [f"# Paper report - {date}", "", "```", stats(st, bench), "```", "", "## Open positions"]
    for s, p in st["positions"].items():
        lines.append(f"- {s}: {p['qty']} @ {p['entry']:.2f} (since {p['date']})")
    lines += ["", "## Orders for tomorrow's open"] + [f"- {o['side']} {o['sym']}" for o in st["pending"]]
    lines += ["", "## Last 10 trades", pd.DataFrame(st["trades"]).tail(10).to_string(index=False) if st["trades"] else "none yet"]
    REPORT.write_text("\n".join(lines))
    print("\n".join(lines))

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "backtest"
    d, b = download("6y" if mode == "backtest" else "1y")
    backtest(d, b) if mode == "backtest" else paper(d, b)
