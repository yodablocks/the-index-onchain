"""Build the five charts in "Trading Fees Have Bought $1.5 Million of Tokenized Stocks, Mostly AI".

Run: python3 make_charts.py  -> writes one HTML file per chart into html/.
Each HTML holds one SVG sized for Medium (1400 px wide); the PNGs in charts/ are screenshots of them.
Reads data/contract_logs.csv.gz, data/buys.csv.gz and data/distributor_logs.csv.gz (plain .csv also works),
as written by fetch_index_hypersync.py. Standard library only, no network.
"""
import gzip
from pathlib import Path

HERE = Path(__file__).parent
DATA, OUT = HERE / "data", HERE / "html"
BLUE, GRAY = "#2a78d6", "#b4b2ab"
INK, INK2, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#8a8984", "#e6e5e0", "#fcfcfb"
FONT = "-apple-system, 'Helvetica Neue', Arial, sans-serif"

# The 18 supported stocks (theindex.finance/#/docs), grouped by theme. Grouping is the author's.
BASKET = [
    ("Chips and memory", ["NVDA", "AMD", "MU", "SNDK", "INTC"], True),
    ("Cloud, compute and AI platforms", ["MSFT", "GOOGL", "AMZN", "META", "ORCL", "CRWV"], True),
    ("AI software", ["PLTR"], True),
    ("Data-center power", ["BE"], True),
    ("Other", ["AAPL", "TSLA", "SPCX", "COIN", "USAR"], False),
]


def rows(name):
    """CSV rows from data/<name>.csv.gz, or data/<name>.csv if not compressed."""
    import csv
    gz = DATA / f"{name}.csv.gz"
    f = gzip.open(gz, "rt", newline="") if gz.exists() else open(DATA / f"{name}.csv", newline="")
    with f:
        yield from csv.DictReader(f)


def page(svg: str, title: str) -> str:
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{title}</title>"
            f"<style>body{{margin:0;background:{SURFACE}}}svg{{display:block}}</style></head>"
            f"<body>{svg}</body></html>")


def text(x, y, s, size=22, fill=INK, weight=400, anchor="start"):
    return (f"<text x='{x}' y='{y}' font-family=\"{FONT}\" font-size='{size}' fill='{fill}' "
            f"font-weight='{weight}' text-anchor='{anchor}'>{s}</text>")


def bar(x, y, w, h, fill):
    # Rounded data end only (right side), square at the baseline.
    r = min(4, w / 2)
    return (f"<path d='M{x},{y} H{x + w - r} Q{x + w},{y} {x + w},{y + r} V{y + h - r} "
            f"Q{x + w},{y + h} {x + w - r},{y + h} H{x} Z' fill='{fill}'/>")


# Chart 3: weekly ETH the treasury spent (equals fees collected; sum matches the site's 816.57 ETH).
# Built from data/contract_logs.csv (HyperSync pull, 2026-10-07), event 0xe0ad67c3..., first data word.
def fees_chart(name) -> str:
    from collections import defaultdict
    from datetime import date, timedelta
    week = defaultdict(float)
    for r in rows(name):
        if r["topic0"].startswith("0xe0ad67c3"):
            d = date.fromisoformat(r["time"][:10])
            week[d - timedelta(days=d.weekday())] += int(r["data"][2:66], 16) / 1e18
    weeks = sorted(week)
    first_day, last_day = date(2026, 7, 3), date(2026, 10, 7)
    partial = {w for w in weeks if w < first_day or w + timedelta(days=6) > last_day}
    full = [w for w in weeks if w not in partial]
    peak = max(full, key=lambda w: week[w])
    latest_full = full[-1]
    drop = 100 * (1 - week[latest_full] / week[peak])
    total = sum(week.values())

    W, H, left, top, bottom = 1400, 760, 110, 190, 600
    vmax = 450
    bw = (W - left - 80) / len(weeks)
    y = lambda v: bottom - (bottom - top) * v / vmax
    parts = [f"<svg xmlns='http://www.w3.org/2000/svg' width='{W}' height='{H}' viewBox='0 0 {W} {H}'>",
             f"<rect width='{W}' height='{H}' fill='{SURFACE}'/>",
             text(60, 70, f"Fee revenue peaked in mid-July and is down {drop:.0f}% since", 34, INK, 600),
             text(60, 112, f"ETH from the 3% $INDEX trading fee, spent by the treasury per week ({total:,.1f} ETH "
                  "since launch)", 22, INK2)]
    for v in range(0, vmax + 1, 100):
        parts.append(f"<line x1='{left}' y1='{y(v)}' x2='{W - 60}' y2='{y(v)}' stroke='{GRID}' stroke-width='1'/>")
        parts.append(text(left - 14, y(v) + 6, f"{v}", 18, MUTED, anchor="end"))
    parts.append(text(left - 14, top - 24, "ETH", 18, MUTED, anchor="end"))
    for i, w in enumerate(weeks):
        v = week[w]
        x = left + i * bw + 3
        h = max(bottom - y(v), 2)
        fill = GRAY if w in partial else BLUE
        r = min(4, (bw - 6) / 2)
        parts.append(f"<path d='M{x},{bottom} V{bottom - h + r} Q{x},{bottom - h} {x + r},{bottom - h} "
                     f"H{x + bw - 6 - r} Q{x + bw - 6},{bottom - h} {x + bw - 6},{bottom - h + r} V{bottom} Z' "
                     f"fill='{fill}'/>")
        if w in (peak, latest_full) or w in partial:
            parts.append(text(x + (bw - 6) / 2, bottom - h - 10, f"{v:,.1f}", 17, INK2, anchor="middle"))
        if i % 2 == 0 or w == weeks[-1]:
            parts.append(text(x + (bw - 6) / 2, bottom + 26, f"{w:%b %d}", 16, MUTED, anchor="middle"))
    parts.append(text(left, bottom + 58, "Week starting (Monday). Gray: partial weeks (launch week from Jul 3; "
                      "current week to Oct 7).", 17, MUTED))
    parts.append(text(60, H - 28, "Source: StockTreasury events on Robinhood Chain via Envio HyperSync, blocks "
                      "1,670,725 to 82,499,236, pulled 2026-10-07. Analysis by Marc Filias.", 16, MUTED))
    parts.append("</svg>")
    return "".join(parts)


# Actual spend per stock: USDG the StockDistributor paid for each stock, matched by log order within each tx.
# Built from data/buys.csv (HyperSync pull, 2026-10-07): each USDG payment is paired with the next stock delivery
# in the same transaction (171,064 pairs, none unmatched).
DISTRIBUTORS = {"0x39adb8acd07427d338b5f1afab436a04abfdb7c4",   # V2, from Jul 28
                "0x2459dedb3012d1e929edd17df26620120bdf11bf"}   # V1 "USDGBuyerDistributor", Jul 9 to 28


def spend_by_stock(name):
    from collections import defaultdict
    bytx = defaultdict(list)
    for r in rows(name):
        if r["symbol"] != "USDG" or r["from"].lower() in DISTRIBUTORS:
            bytx[r["tx"]].append(r)
    spent, pending = defaultdict(float), None
    for rs in bytx.values():
        rs.sort(key=lambda r: int(r["log_index"]))
        for r in rs:
            if r["symbol"] == "USDG":
                pending = float(r["amount"])
            elif pending is not None:
                spent[r["symbol"]] += pending
                pending = None
    return spent


def basket_spend_chart(spent) -> str:
    total = sum(spent.values())
    groups = [(name, tickers, is_ai, sum(spent[t] for t in tickers)) for name, tickers, is_ai in BASKET]
    ai = sum(v for *_, is_ai, v in groups if is_ai)
    W, H, left, top, row = 1400, 690, 420, 170, 76
    scale = 1000 / 100 * 0.62  # px per percentage point
    parts = [f"<svg xmlns='http://www.w3.org/2000/svg' width='{W}' height='{H}' viewBox='0 0 {W} {H}'>",
             f"<rect width='{W}' height='{H}' fill='{SURFACE}'/>",
             text(60, 70, f"{100 * ai / total:.0f}% of the money bought AI-linked stocks", 34, INK, 600),
             text(60, 112, f"Share of the {total:,.0f} USDG the distributors spent on stocks, "
                  "Jul 9 to Oct 7, 2026, by theme", 22, INK2)]
    for v in range(0, 61, 10):
        gx = left + v * scale
        parts.append(f"<line x1='{gx}' y1='{top - 20}' x2='{gx}' y2='{top + row * len(groups) - 10}' "
                     f"stroke='{GRID}' stroke-width='1'/>")
        parts.append(text(gx, top + row * len(groups) + 18, f"{v}%", 18, MUTED, anchor="middle"))
    for i, (name, tickers, is_ai, v) in enumerate(groups):
        y = top + i * row
        pct = 100 * v / total
        parts.append(text(left - 20, y + 30, name, 22, INK, 500, "end"))
        parts.append(bar(left, y + 4, max(pct * scale - 2, 3), 40, BLUE if is_ai else GRAY))
        parts.append(text(left + pct * scale + 14, y + 31, f"{pct:.1f}%  ({', '.join(tickers)})", 19, INK2))
    parts.append(text(left, top + row * len(groups) + 46, "Share of USDG spent", 18, MUTED))
    parts.append(text(60, H - 28, "Source: USDG payments by both distributor versions on Robinhood Chain via Envio HyperSync, "
                      "pulled 2026-10-08. Grouping by Marc Filias; BE counted as data-center power.", 16, MUTED))
    parts.append("</svg>")
    return "".join(parts)


def weights_chart(spent) -> str:
    total = sum(spent.values())
    items = sorted(spent.items(), key=lambda kv: -kv[1])
    equal = 100 / len(items)
    top3 = sum(v for _, v in items[:3]) / total * 100
    W, H, left, top, row = 1400, 1110, 150, 190, 42
    vmax = 20
    scale = (W - left - 200) / vmax
    parts = [f"<svg xmlns='http://www.w3.org/2000/svg' width='{W}' height='{H}' viewBox='0 0 {W} {H}'>",
             f"<rect width='{W}' height='{H}' fill='{SURFACE}'/>",
             text(60, 70, f"Weighted, not equal: three stocks took {top3:.0f}% of the money", 34, INK, 600),
             text(60, 112, f"Share of {total:,.0f} USDG spent per stock, Jul 9 to Oct 7, 2026. The line marks an "
                  f"equal split across 18 ({equal:.1f}% each)", 22, INK2)]
    for v in range(0, vmax + 1, 5):
        gx = left + v * scale
        parts.append(f"<line x1='{gx}' y1='{top - 20}' x2='{gx}' y2='{top + row * len(items) - 4}' "
                     f"stroke='{GRID}' stroke-width='1'/>")
        parts.append(text(gx, top + row * len(items) + 18, f"{v}%", 18, MUTED, anchor="middle"))
    for i, (sym, v) in enumerate(items):
        y = top + i * row
        pct = 100 * v / total
        parts.append(text(left - 16, y + 24, sym, 20, INK, 500, "end"))
        parts.append(bar(left, y + 6, max(pct * scale - 2, 3), 26, BLUE))
        parts.append(text(left + pct * scale + 12, y + 26, f"{pct:.1f}%", 18, INK2))
    ex = left + equal * scale
    parts.append(f"<line x1='{ex}' y1='{top - 30}' x2='{ex}' y2='{top + row * len(items) - 4}' "
                 f"stroke='{INK}' stroke-width='2'/>")
    parts.append(text(ex + 8, top - 34, f"equal split, {equal:.1f}%", 18, INK, 500))
    parts.append(text(left, top + row * len(items) + 46, "Share of USDG spent", 18, MUTED))
    parts.append(text(60, H - 50, "The site says: “Each buy splits ETH equally across all 18 supported "
                      "stocks” (theindex.finance/#/distributions, read 2026-10-07).", 17, INK2))
    parts.append(text(60, H - 22, "Source: 171,064 USDG payments by both distributor versions, each matched to the stock "
                      "it bought; Robinhood Chain via Envio HyperSync, pulled 2026-10-08.", 16, MUTED))
    parts.append("</svg>")
    return "".join(parts)


# Payout history from the distributors' own Distributed(stock, amount, holders) events (all four distributors,
# addresses from The Index's DefiLlama adapter). data/distributor_logs.csv, HyperSync pull 2026-10-08.
DISTRIBUTED = "0x60ce3cc2d133631eac66a476f14997a9fa682bd05a60dd993cf02285822d78d8"


def payouts(name):
    from datetime import datetime
    first = {}
    for r in rows(name):
        if r["topic0"] == DISTRIBUTED and r["tx"] not in first:
            first[r["tx"]] = (datetime.fromisoformat(r["time"]), int(r["data"][66:130], 16))
    return sorted(first.values())


def payouts_per_week_chart(pts) -> str:
    from collections import Counter
    from datetime import date, timedelta
    wk = Counter()
    for t, _ in pts:
        d = t.date()
        wk[d - timedelta(days=d.weekday())] += 1
    weeks = sorted(wk)
    last_day = pts[-1][0].date()
    partial = {w for w in weeks if w < date(2026, 7, 3) or w + timedelta(days=6) > last_day}
    W, H, left, top, bottom = 1400, 760, 110, 190, 600
    vmax = max(wk.values()) * 1.1
    step = 200 if vmax > 600 else 100
    bw = (W - left - 80) / len(weeks)
    y = lambda v: bottom - (bottom - top) * v / vmax
    full = [w for w in weeks if w not in partial]
    first_full, last_full = full[0], full[-1]
    parts = [f"<svg xmlns='http://www.w3.org/2000/svg' width='{W}' height='{H}' viewBox='0 0 {W} {H}'>",
             f"<rect width='{W}' height='{H}' fill='{SURFACE}'/>",
             text(60, 70, "From every 15 minutes to every two days", 34, INK, 600),
             text(60, 112, f"Stock payouts to $INDEX holders per week ({len(pts):,} payouts since Jul 3). "
                  "Median gap: 16 min in July, 47 h in October", 22, INK2)]
    v = 0
    while v <= vmax:
        parts.append(f"<line x1='{left}' y1='{y(v)}' x2='{W - 60}' y2='{y(v)}' stroke='{GRID}' stroke-width='1'/>")
        parts.append(text(left - 14, y(v) + 6, f"{v:,}", 18, MUTED, anchor="end"))
        v += step
    for i, w in enumerate(weeks):
        n = wk[w]
        x = left + i * bw + 3
        h = max(bottom - y(n), 2)
        r = min(4, (bw - 6) / 2)
        parts.append(f"<path d='M{x},{bottom} V{bottom - h + r} Q{x},{bottom - h} {x + r},{bottom - h} "
                     f"H{x + bw - 6 - r} Q{x + bw - 6},{bottom - h} {x + bw - 6},{bottom - h + r} V{bottom} Z' "
                     f"fill='{GRAY if w in partial else BLUE}'/>")
        if w in (first_full, last_full) or w in partial or n == max(wk.values()):
            parts.append(text(x + (bw - 6) / 2, bottom - h - 10, f"{n:,}", 17, INK2, anchor="middle"))
        if i % 2 == 0 or w == weeks[-1]:
            parts.append(text(x + (bw - 6) / 2, bottom + 26, f"{w:%b %d}", 16, MUTED, anchor="middle"))
    parts.append(text(left, bottom + 58, f"Week starting (Monday). Gray: partial weeks (launch week from Jul 3; "
                      f"current week to {last_day:%b} {last_day.day}).", 17, MUTED))
    parts.append(text(60, H - 28, "Source: Distributed events of the four $INDEX distributors on Robinhood Chain "
                      "via Envio HyperSync, pulled 2026-10-08. Analysis by Marc Filias.", 16, MUTED))
    parts.append("</svg>")
    return "".join(parts)


def holders_chart(pts) -> str:
    from datetime import datetime, timezone
    W, H, left, top, bottom, right = 1400, 760, 110, 190, 600, 1320
    t0, t1 = pts[0][0], pts[-1][0]
    span = (t1 - t0).total_seconds()
    vmax = 4500
    x = lambda t: left + (right - left) * (t - t0).total_seconds() / span
    y = lambda v: bottom - (bottom - top) * v / vmax
    peak = max(pts, key=lambda p: p[1])
    path = " ".join(f"{'M' if i == 0 else 'L'}{x(t):.1f},{y(h):.1f}" for i, (t, h) in enumerate(pts))
    parts = [f"<svg xmlns='http://www.w3.org/2000/svg' width='{W}' height='{H}' viewBox='0 0 {W} {H}'>",
             f"<rect width='{W}' height='{H}' fill='{SURFACE}'/>",
             text(60, 70, "Eligible wallets kept rising long after the fee peak", 34, INK, 600),
             text(60, 112, f"Wallets eligible for each payout (above 10,000 $INDEX): {pts[0][1]} at launch, "
                  f"peak {peak[1]:,} on {peak[0]:%b} {peak[0].day}, {pts[-1][1]:,} on {t1:%b} {t1.day}", 22, INK2)]
    for v in range(0, vmax + 1, 1000):
        parts.append(f"<line x1='{left}' y1='{y(v)}' x2='{right}' y2='{y(v)}' stroke='{GRID}' stroke-width='1'/>")
        parts.append(text(left - 14, y(v) + 6, f"{v:,}", 18, MUTED, anchor="end"))
    for m in range(7, 11):
        t = datetime(2026, m, 1, tzinfo=timezone.utc)
        if t0 <= t <= t1:
            parts.append(text(x(t), bottom + 26, f"{t:%b} 1", 16, MUTED, anchor="middle"))
    parts.append(f"<path d='{path}' fill='none' stroke='{BLUE}' stroke-width='2'/>")
    for t, h in (pts[0], peak, pts[-1]):
        parts.append(f"<circle cx='{x(t):.1f}' cy='{y(h):.1f}' r='5' fill='{BLUE}' stroke='{SURFACE}' stroke-width='2'/>")
    parts.append(text(x(peak[0]), y(peak[1]) - 14, f"{peak[1]:,}", 17, INK2, anchor="middle"))
    parts.append(text(x(pts[-1][0]) - 8, y(pts[-1][1]) + 30, f"{pts[-1][1]:,}", 17, INK2, anchor="end"))
    parts.append(text(x(pts[0][0]) + 10, y(pts[0][1]) - 12, f"{pts[0][1]}", 17, INK2))
    parts.append(text(60, H - 28, "Source: holder counts in the Distributed events of the four $INDEX distributors, "
                      "Robinhood Chain via Envio HyperSync, pulled 2026-10-08.", 16, MUTED))
    parts.append("</svg>")
    return "".join(parts)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    charts = [("weekly-fees", "Weekly fees", fees_chart("contract_logs"))]
    spent = spend_by_stock("buys")
    charts += [("basket-by-spend", "Basket by spend", basket_spend_chart(spent)),
               ("stock-weights", "Stock weights", weights_chart(spent))]
    pts = payouts("distributor_logs")
    charts += [("payouts-per-week", "Payouts per week", payouts_per_week_chart(pts)),
               ("holders", "Eligible holders", holders_chart(pts))]
    for name, title, svg in charts:
        (OUT / f"{name}.html").write_text(page(svg, title))
        print("wrote", OUT / f"{name}.html")
