"""Pull The Index's onchain history through Envio HyperSync, within a 15 requests/minute limit.

One paginated query returns every log we need plus block timestamps, so the whole history takes
a handful of requests instead of tens of thousands. Standard library only. Run it yourself:

    python3 fetch_index_hypersync.py --out data                       # core: fee hook and treasury events
    python3 fetch_index_hypersync.py --out data --part buys           # USDG payments and stocks bought
    python3 fetch_index_hypersync.py --out data --part distributions  # payouts of the four distributors

Needs ENVIO_API_TOKEN in the environment (free token from the Envio dashboard; never written to disk).
Token decimals are read with eth_call requests to the public Robinhood Chain RPC (HyperSync has no eth_call).

Writes, under --out:
    contract_logs.csv      every event from the fee hook and the treasury (raw topics and data)
    topics.txt             event signatures per contract, with counts (for decoding)
    buys.csv               USDG out of the treasury, USDG and stocks in and out of the two USDG-era distributors
    distributor_logs.csv   Distributed(stock, amount, holders) and per-round events of the four distributors
    distributor_topics.txt event counts per distributor
    fetch_log.txt          endpoint, block range, request count and run time, for citing numbers
"""
import argparse
import csv
import http.client
import json
import os
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HYPERSYNC = "https://robinhood.hypersync.xyz/query"
PUBLIC_RPC = "https://rpc.mainnet.chain.robinhood.com"
UA = "index-article-research/1.0 (python stdlib)"
TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
LAUNCH_BLOCK = 1_670_725  # $INDEX creation tx 0xf3c73adb..., 2026-07-03 02:55:52 UTC
INDEX = "0x56910D4409F3a0C78C64DD8D0545FF0705389870"  # the $INDEX token (for reference; not queried)
CONTRACTS = {
    "IndexFeeHook": "0x2cD91bD228ff4c537031d6b8204782090c84c0cC",
    "StockTreasury": "0x1604Ff11dFeAaC437077aEDA2FA492ac9EC804dF",
}
DISTRIBUTOR_V2 = "0x39ADB8acD07427D338b5f1AfAb436A04AbFdB7c4"  # "StockDistributor" in the docs; from Jul 28
STOCKS = {
    "AAPL": "0xaf3d76f1834a1d425780943c99ea8a608f8a93f9", "AMD": "0x86923f96303d656e4aa86d9d42d1e57ad2023fdc",
    "AMZN": "0x12f190a9f9d7d37a250758b26824b97ce941bf54", "BE": "0x822cc93ffd030293e9842c30bbd678f530701867",
    "COIN": "0x6330d8c3178a418788df01a47479c0ce7ccf450b", "CRWV": "0x5f10a1c971b69e47e059e1dc91901b59b3fb49c3",
    "GOOGL": "0x2e0847e8910a9732eb3fb1bb4b70a580adad4fe3", "INTC": "0xc72b96e0e48ecd4dc75e1e45396e26300bc39681",
    "META": "0xc0d6457c16cc70d6790dd43521c899c87ce02f35", "MSFT": "0xe93237c50d904957cf27e7b1133b510c669c2e74",
    "MU": "0xff080c8ce2e5feadaca0da81314ae59d232d4afd", "NVDA": "0xd0601ce157db5bdc3162bbac2a2c8af5320d9eec",
    "ORCL": "0xb0992820e760d836549ba69bc7598b4af75dee03", "PLTR": "0x894e1ec2d74ffe5aef8dc8a9e84686accb964f2a",
    "SNDK": "0xb90a19ff0af67f7779aff50a882a9cff42446400", "SPCX": "0x4a0e65a3eccec6dbe60ae065f2e7bb85fae35eea",
    "TSLA": "0x322f0929c4625ed5bad873c95208d54e1c003b2d", "USAR": "0xd917b029c761d264c6a312bbbcda868658ef86a6",
}
DISTRIBUTOR_V1 = "0x2459DedB3012d1E929EdD17DF26620120bDF11bf"  # "USDGBuyerDistributor", Jul 9 to 28
# All four "legacy" $INDEX distributors, from The Index's DefiLlama adapter (DefiLlama/dimension-adapters PR 8666).
LEGACY_DISTRIBUTORS = ["0x33B0095333e64bf375952eF197b6FDC3437dc014", "0x02241379056fd5c2BDe0bDfc63D2b272C18A49bE",
                       "0x2459DedB3012d1E929EdD17DF26620120bDF11bf", "0x39ADB8acD07427D338b5f1AfAb436A04AbFdB7c4"]
USDG = "0x5fc5360D0400a0Fd4f2af552ADD042D716F1d168"  # Global Dollar; the treasury swaps ETH fees into it since 2026-07-09
SYMBOL = {v.lower(): k for k, v in STOCKS.items()} | {USDG.lower(): "USDG"}
CONTRACT_OF = {v.lower(): k for k, v in CONTRACTS.items()}
MIN_INTERVAL = 4.5  # seconds between HyperSync requests: about 13 per minute, under the 15 rpm limit


def post(url, payload, headers, label):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, body, {"content-type": "application/json", "user-agent": UA, **headers})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            text = e.read(400).decode("utf-8", "replace")
            if e.code == 429:
                print(f"\n  rate limited by {label}; waiting 60s")
                time.sleep(60)
                continue
            if e.code < 500:
                raise SystemExit(f"HTTP {e.code} from {label}: {text}")
            print(f"\n  {label} HTTP {e.code}; retry in {2 ** attempt}s")
            time.sleep(2 ** attempt)
        except (OSError, http.client.HTTPException, json.JSONDecodeError) as e:  # dropped or cut-off responses
            print(f"\n  {label}: {type(e).__name__}; retry in {2 ** attempt}s")
            time.sleep(2 ** attempt)
    raise SystemExit(f"{label} kept failing; run again later")


def topics_of(lg):
    if "topics" in lg and lg["topics"] is not None:
        t = [x for x in lg["topics"] if x]
    else:
        t = [lg.get(f"topic{i}") for i in range(4)]
        t = [x for x in t if x]
    return t


def as_int(x):
    if isinstance(x, int):
        return x
    return int(x, 16) if isinstance(x, str) and x.startswith("0x") else int(x)


def topic_addr(t):
    return "0x" + t[-40:]


def hypersync(token, start, requests, checkpoint, part):
    treasury_topic = "0x" + "0" * 24 + CONTRACTS["StockTreasury"][2:].lower()
    if part == "core":  # fee hook and treasury events: small, fast
        selections = [{"address": list(CONTRACTS.values())}]
    elif part == "buys":  # USDG leaving the treasury, and stocks arriving at the distributors (the buys)
        dist = ["0x" + "0" * 24 + d[2:].lower() for d in (DISTRIBUTOR_V2, DISTRIBUTOR_V1)]
        selections = [
            {"address": [USDG], "topics": [[TRANSFER], [treasury_topic]]},
            {"address": [USDG], "topics": [[TRANSFER], dist]},       # USDG paid out per stock buy (V1 and V2)
            {"address": [USDG], "topics": [[TRANSFER], [], dist]},   # USDG arriving from fee swaps
            {"address": list(STOCKS.values()), "topics": [[TRANSFER], [], dist]},
        ]
    else:  # distributions: Distributed(stock, amount, holders) and the per-round event; skips per-batch events
        selections = [{"address": LEGACY_DISTRIBUTORS, "topics": [[
            "0x60ce3cc2d133631eac66a476f14997a9fa682bd05a60dd993cf02285822d78d8",
            "0x0e41c903d4f464af8fdd82a2a195fb81a5b17cfe3a20585d2f10d0eeb1f1d33c"]]}]
    query = {
        "from_block": start,
        "logs": selections,
        "max_num_logs": 10_000,  # smaller pages: fewer cut-off responses
        "field_selection": {
            "block": ["number", "timestamp"],
            "log": ["block_number", "log_index", "transaction_hash", "address", "data",
                    "topic0", "topic1", "topic2", "topic3"],
        },
    }
    headers = {"authorization": f"Bearer {token}"}
    logs, times, last = [], {}, 0.0
    height = None
    if checkpoint.exists():
        state = json.loads(checkpoint.read_text())
        if state.get("part") == part:
            logs, times = state["logs"], {int(k): v for k, v in state["times"].items()}
            query["from_block"], requests[0] = state["next_block"], state["requests"]
            print(f"  resuming from checkpoint at block {query['from_block']:,} ({len(logs):,} logs so far)")
    while True:
        wait = MIN_INTERVAL - (time.monotonic() - last)
        if wait > 0:
            time.sleep(wait)
        last = time.monotonic()
        res = post(HYPERSYNC, query, headers, "envio hypersync")
        requests[0] += 1
        height = res.get("archive_height", height)
        batches = res.get("data") or []
        if isinstance(batches, dict):
            batches = [batches]
        for b in batches:
            for blk in b.get("blocks") or []:
                times[as_int(blk["number"])] = as_int(blk["timestamp"])
            logs.extend(b.get("logs") or [])
        nxt = res.get("next_block")
        tmp = checkpoint.with_suffix(".tmp")
        tmp.write_text(json.dumps({"next_block": nxt, "requests": requests[0], "part": part,
                                   "logs": logs, "times": times}))
        tmp.replace(checkpoint)
        print(f"  request {requests[0]}: up to block {nxt:,} of {height:,}, {len(logs):,} logs", end="\r")
        if nxt is None or (height is not None and nxt >= height) or nxt <= query["from_block"]:
            break
        query["from_block"] = nxt
    print()
    return logs, times, height


def decimals(token):
    payload = {"jsonrpc": "2.0", "id": 1, "method": "eth_call", "params": [{"to": token, "data": "0x313ce567"}, "latest"]}
    res = post(PUBLIC_RPC, payload, {}, "public rpc")
    if "result" not in res:
        raise SystemExit(f"decimals() failed for {token}: {res.get('error')}")
    return int(res["result"], 16)


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat() if ts is not None else ""


def write(path, rows, fields):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"  {path.name}: {len(rows):,} rows")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data")
    ap.add_argument("--from-block", type=int, default=LAUNCH_BLOCK)
    ap.add_argument("--part", choices=["core", "buys", "distributions"], default="core",
                    help="core: fee hook and treasury events; buys: USDG payments and stocks bought; "
                         "distributions: payouts of the four distributors")
    a = ap.parse_args()
    token = os.environ.get("ENVIO_API_TOKEN")
    if not token:
        raise SystemExit("needs ENVIO_API_TOKEN in the environment")
    out = Path(a.out)
    out.mkdir(exist_ok=True)
    started, requests = datetime.now(timezone.utc), [0]

    print(f"querying HyperSync from block {a.from_block:,}")
    checkpoint = out / f"hypersync_{a.part}.json"
    logs, times, height = hypersync(token, a.from_block, requests, checkpoint, a.part)

    print("token decimals (public RPC)")
    dec = {}
    need = list(STOCKS.values()) + [USDG] if a.part == "buys" else []
    for addr in need:
        dec[addr.lower()] = decimals(addr)
        time.sleep(0.5)
    if dec:
        print("  ", {SYMBOL[k]: v for k, v in dec.items()})

    contract_rows, stock_rows = [], []
    missing_time = 0
    for lg in sorted(logs, key=lambda l: (as_int(l["block_number"]), as_int(l["log_index"]))):
        address = lg["address"].lower()
        t = topics_of(lg)
        block = as_int(lg["block_number"])
        ts = times.get(block)
        missing_time += ts is None
        base = {"block": block, "time": iso(ts), "tx": lg["transaction_hash"]}
        if a.part == "distributions":
            contract_rows.append({**base, "contract": address, "log_index": as_int(lg["log_index"]),
                                  "topic0": (t + [""] * 4)[0], "topic1": (t + [""] * 4)[1],
                                  "topic2": (t + [""] * 4)[2], "topic3": (t + [""] * 4)[3], "data": lg.get("data", "")})
        elif address in CONTRACT_OF:
            contract_rows.append({**base, "contract": CONTRACT_OF[address], "log_index": as_int(lg["log_index"]),
                                  "topic0": (t + [""] * 4)[0], "topic1": (t + [""] * 4)[1],
                                  "topic2": (t + [""] * 4)[2], "topic3": (t + [""] * 4)[3], "data": lg.get("data", "")})
        elif address in SYMBOL and len(t) == 3:
            stock_rows.append({**base, "log_index": as_int(lg["log_index"]), "symbol": SYMBOL[address],
                               "from": topic_addr(t[1]), "to": topic_addr(t[2]),
                               "amount": int(lg["data"], 16) / 10 ** dec[address]})

    print("writing")
    if a.part == "core":
        write(out / "contract_logs.csv", contract_rows,
              ["contract", "block", "time", "tx", "log_index", "topic0", "topic1", "topic2", "topic3", "data"])
        with open(out / "topics.txt", "w") as f:
            for name in CONTRACTS:
                f.write(f"{name}\n")
                for tp, n in Counter(r["topic0"] for r in contract_rows if r["contract"] == name).most_common():
                    f.write(f"  {n:>7,}  {tp}\n")
    elif a.part == "distributions":
        write(out / "distributor_logs.csv", contract_rows,
              ["contract", "block", "time", "tx", "log_index", "topic0", "topic1", "topic2", "topic3", "data"])
        with open(out / "distributor_topics.txt", "w") as f:
            for (c, tp), n in Counter((r["contract"], r["topic0"]) for r in contract_rows).most_common():
                f.write(f"{n:>8,}  {c}  {tp}\n")
    else:
        write(out / "buys.csv", stock_rows, ["block", "time", "tx", "log_index", "symbol", "from", "to", "amount"])
    with open(out / "fetch_log.txt", "a") as f:
        f.write(f"{started.isoformat()} source=envio-hypersync part={a.part} blocks={a.from_block}..{height} "
                f"requests={requests[0]} logs={len(logs)} missing_block_times={missing_time}\n")
    if missing_time:
        print(f"note: {missing_time:,} logs have no block time (HyperSync returned no block row for them)")
    print(f"done: {requests[0]} HyperSync requests, blocks {a.from_block:,} to {height:,}")


if __name__ == "__main__":
    main()
