# hledger-inventory

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A small, plain-text inventory and bookkeeping system built on [hledger](https://hledger.org), plus a helper script for inventory valuation reports.

It tracks physical goods (received, stored, shipped, sold, written off) alongside the corresponding money-side bookkeeping (accounts payable/receivable, VAT, cost of goods sold) in a single double-entry ledger.

## How it works

Inventory quantities are tracked as commodities (e.g. `WIDGET`, `GADGET`) moving between accounts that represent physical locations and pipeline stages:

```
Supplier -> InTransit -> Inbound dock -> Bin (storage location)
Bin -> Outbound staging -> Shipped -> Delivered/Invoiced (AR) -> Paid
Any stage -> broken/damaged -> written off
```

Each stage is its own account under `Assets:Inventory:...`, so a `hledger balance` on that account tree shows exactly how much stock is at each step and where it physically sits (which bin, in transit, shipped, etc).

## Files

| File | Purpose |
|---|---|
| `main.journal` | Entry point: commodity/account declarations, includes all other files |
| `opening.journal` | Opening balances |
| `purchasing.journal` | Purchase orders from suppliers and paying supplier invoices |
| `transfers.journal` | Movement of goods between pipeline stages (inbound → bin → outbound → shipped) |
| `invoicing.journal` | Customer invoices, cost of goods sold, VAT on sales, customer payments |
| `damaged.journal` | Write-offs for broken/damaged stock, from whichever stage it's found at |
| `prices.journal` | Market price history per commodity, used for valuation (`-V`) |
| `inventory_report.py` | Combined quantity/cost/market-value inventory report (see below) |

Run hledger against `main.journal`, e.g.:

```sh
hledger -f main.journal balance Assets:Inventory
hledger -f main.journal check accounts
```

or set `export LEDGER_FILE=main.journal` to omit `-f main.journal` each time.

## Inventory report

`inventory_report.py` combines hledger's quantity, cost, and market-value balance reports for inventory accounts into one table, grouped by commodity, with a totals line per commodity and a grand total across all commodities.

```
Usage:
    ./inventory_report.py [ACCOUNT_QUERY] [-f JOURNAL_FILE] [--csv]
                          [--commodity COMMODITY[,COMMODITY...]] [-h|--help]

Arguments:
    ACCOUNT_QUERY     hledger account query to report on (default: Assets:Inventory)
    -f JOURNAL_FILE   journal file to read (default: main.journal)
    --csv             output plain CSV (one row per account/commodity, no
                       totals) instead of the aligned text table
    --commodity LIST  only report on these commodities, comma-separated
                       (e.g. WIDGET or WIDGET,GADGET). Default: all
                       commodities found in ACCOUNT_QUERY
    -h, --help        show this help message and exit
```

Example:

```
$ ./inventory_report.py
Account                             Quantity        Cost  Market Value
---------------------------------  ---------  ----------  ------------
Assets:Inventory:Warehouse:Bin:B1   7 GADGET   70.00 EUR    105.00 EUR
Assets:Inventory:Warehouse:Bin:B2   7 GADGET   70.00 EUR    105.00 EUR
Total (GADGET):                    14 GADGET  140.00 EUR    210.00 EUR
---------------------------------  ---------  ----------  ------------
Assets:Inventory:Warehouse:Bin:A1  37 WIDGET  148.00 EUR    259.00 EUR
Total (WIDGET):                    37 WIDGET  148.00 EUR    259.00 EUR
---------------------------------  ---------  ----------  ------------
Total (all commodities):                      288.00 EUR    469.00 EUR
```

- **Cost** is the balance at booked (transaction) cost (`hledger -B`).
- **Market Value** uses the latest known market price per commodity (`hledger -V`), from `prices.journal`.

Other examples:

```sh
./inventory_report.py Assets:Inventory:Warehouse       # only warehouse accounts
./inventory_report.py --commodity WIDGET               # only one commodity
./inventory_report.py --csv > inventory.csv             # CSV, one row per account/commodity
```

## Requirements

- [hledger](https://hledger.org) on your `PATH`
- Python 3.10+ (for `inventory_report.py`)
