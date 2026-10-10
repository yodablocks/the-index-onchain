# the-index-onchain

Data and code behind the article "Trading Fees Have Bought $1.5 Million of Tokenized Stocks, Mostly AI. I Read the Chain to See What Holders Actually Got." (Medium, October 2026).

It reads the history of The Index ($INDEX, theindex.finance) on Robinhood Chain from event logs: the trading fees the treasury spent, what the distributor contracts paid for each stock, and every payout to holders.

Not financial advice. I don't hold $INDEX and have no relationship with the team.

## What is here

| Path | What it is |
|---|---|
| `fetch_index_hypersync.py` | Pulls the event logs through Envio HyperSync and writes the CSVs in `data/` |
| `make_charts.py` | Builds the five charts from those CSVs, as SVG in HTML (`html/`) |
| `charts/` | The five chart images used in the article (screenshots of the HTML) |
| `data/contract_logs.csv.gz` | Every event of the fee hook and the StockTreasury: 12,693 logs |
| `data/buys.csv.gz` | USDG out of the treasury, and USDG and stock transfers in and out of the two USDG-era distributors: 354,485 transfers |
| `data/distributor_logs.csv.gz` | `Distributed(stock, amount, holders)` and per-round events of the four distributors: 46,229 logs |
| `data/topics.txt`, `data/distributor_topics.txt` | Event counts per contract and topic, for decoding |
| `data/fetch_log.txt` | Block range, request count and time of each pull |

All data was pulled on October 7 and 8, 2026, from block 1,670,725 (the $INDEX creation, July 3, 2026).

## Reproduce the charts (no network)

```
python3 make_charts.py
```

Python 3.10 or later, standard library only. It reads the compressed CSVs directly and writes `html/*.html`. Open them in a browser; each is one 1400 px wide SVG.

## Pull the data again

```
export ENVIO_API_TOKEN=...   # free token from the Envio dashboard
python3 fetch_index_hypersync.py --out data
python3 fetch_index_hypersync.py --out data --part buys
python3 fetch_index_hypersync.py --out data --part distributions
```

- The free Envio plan allows 15 requests per minute; the script waits 4.5 seconds between requests. The three parts take a few minutes in total.
- Token decimals are read from the public Robinhood Chain RPC.
- The script saves a checkpoint (`data/hypersync_<part>.json`) after each request and resumes from it if stopped. Delete the checkpoint to start over.
- It writes plain `.csv`; `make_charts.py` reads either `.csv` or `.csv.gz`. A new pull will include blocks after October 8, so the numbers will differ from the article.

## Method notes

- **Fees:** the treasury emits one event per spend (`0xe0ad67c3...`); the first data word is the ETH spent. The total, 816.67 ETH, matches the 816.57 ETH shown on theindex.finance on October 7.
- **Spend per stock:** within each transaction, each USDG payment by a distributor is paired with the next stock delivery, by log order. 171,064 pairs, none unmatched. Distributors: `0x2459DedB3012d1E929EdD17DF26620120bDF11bf` (July 9 to 28) and `0x39ADB8acD07427D338b5f1AfAb436A04AbFdB7c4` (from July 28).
- **Payouts and holders:** the first `Distributed` event of each transaction counts as one payout; its third field is the number of holders paid. The four distributor addresses come from The Index's DefiLlama adapter (DefiLlama/dimension-adapters PR 8666).
- **Theme grouping** in the basket chart is mine. BE (Bloom Energy) is counted as data-center power.
- `data/distributor_logs.csv.gz` was filtered from a pull of every distributor event (80,968 logs, see `fetch_log.txt`) to the two topics the current script requests. The charts are the same either way.

## License

MIT, see `LICENSE`. The data is public blockchain data.
