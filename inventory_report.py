#!/usr/bin/env python3
"""Combine hledger's quantity, cost, and market-value balance reports for
inventory accounts into one table, grouped by commodity with its own totals
line per commodity, plus a grand total across all commodities at the bottom.

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

Examples:
    ./inventory_report.py
    ./inventory_report.py Assets:Inventory:Warehouse
    ./inventory_report.py -f main.journal Assets:Inventory
    ./inventory_report.py --csv > inventory.csv
    ./inventory_report.py --commodity WIDGET
    ./inventory_report.py --commodity WIDGET,GADGET
"""

import csv
import io
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal


def run_bal(journal_file, query, commodity, extra_args):
    cmd = ["hledger", "-f", journal_file, "bal", query, "--layout=bare", "-O", "csv", *extra_args]
    if commodity is not None:
        cmd.append(f"cur:^{re.escape(commodity)}$")
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return list(csv.DictReader(io.StringIO(result.stdout)))


def commodities_in(journal_file, query):
    rows = run_bal(journal_file, query, None, [])
    seen = []
    for row in rows:
        if row["commodity"] not in seen:
            seen.append(row["commodity"])
    return seen


def commodity_rows(journal_file, query, commodity):
    """Per-account rows for one commodity, plus its totals (for the text report)."""
    qty_rows = run_bal(journal_file, query, commodity, [])
    cost_rows = run_bal(journal_file, query, commodity, ["-B"])
    value_rows = run_bal(journal_file, query, commodity, ["-V"])

    cost = {row["account"]: f'{row["balance"]} {row["commodity"]}' for row in cost_rows}
    value = {row["account"]: f'{row["balance"]} {row["commodity"]}' for row in value_rows}

    account_rows = []
    total_row = None
    for row in qty_rows:
        if row["account"] == "Total:":
            total_row = row
            continue
        account = row["account"]
        account_rows.append(
            {
                "account": account,
                "commodity": commodity,
                "quantity": row["balance"],
                "cost": cost.get(account, ""),
                "value": value.get(account, ""),
            }
        )

    cost_total_row = next((row for row in cost_rows if row["account"] == "Total:"), None)
    value_total_row = next((row for row in value_rows if row["account"] == "Total:"), None)
    return account_rows, total_row, cost_total_row, value_total_row


def text_group(commodity, account_rows, total_row, cost_total_row, value_total_row):
    group = [
        (
            row["account"],
            f'{row["quantity"]} {row["commodity"]}',
            row["cost"],
            row["value"],
        )
        for row in account_rows
    ]
    if total_row is not None:
        group.append(
            (
                f"Total ({commodity}):",
                f'{total_row["balance"]} {total_row["commodity"]}',
                cost_total_row["balance"] + " " + cost_total_row["commodity"] if cost_total_row else "",
                value_total_row["balance"] + " " + value_total_row["commodity"] if value_total_row else "",
            )
        )
    return group


def parse_amount(row):
    return Decimal(row["balance"].replace(",", "")), row["commodity"]


def format_sums(sums):
    return " + ".join(f"{amount:.2f} {currency}" for currency, amount in sums.items())


def print_table(groups, grand_total_row):
    headers = ("Account", "Quantity", "Cost", "Market Value")
    all_rows = [row for group in groups for row in group] + [grand_total_row]
    widths = [len(h) for h in headers]
    for row in all_rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def fmt_row(row):
        cols = []
        for i, cell in enumerate(row):
            if i == 0:
                cols.append(cell.ljust(widths[i]))
            else:
                cols.append(cell.rjust(widths[i]))
        return "  ".join(cols)

    separator = "  ".join("-" * w for w in widths)
    print(fmt_row(headers))
    print(separator)
    for group in groups:
        for row in group:
            print(fmt_row(row))
        print(separator)
    print(fmt_row(grand_total_row))


def print_csv(all_account_rows):
    headers = ("Account", "Commodity", "Quantity", "Cost", "Market Value")
    writer = csv.writer(sys.stdout)
    writer.writerow(headers)
    for row in all_account_rows:
        writer.writerow((row["account"], row["commodity"], row["quantity"], row["cost"], row["value"]))


@dataclass
class Args:
    journal_file: str
    query: str
    csv_output: bool
    wanted_commodities: set | None


def parse_args(argv):
    argv = list(argv)
    journal_file = "main.journal"
    if "-f" in argv:
        i = argv.index("-f")
        journal_file = argv[i + 1]
        del argv[i : i + 2]
    csv_output = "--csv" in argv
    if csv_output:
        argv.remove("--csv")
    wanted_commodities = None
    if "--commodity" in argv:
        i = argv.index("--commodity")
        wanted_commodities = set(argv[i + 1].split(","))
        del argv[i : i + 2]
    query = argv[0] if argv else "Assets:Inventory"
    return Args(journal_file, query, csv_output, wanted_commodities)


def resolve_commodities(available_commodities, wanted_commodities):
    if wanted_commodities is None:
        return sorted(available_commodities)
    unknown = wanted_commodities - set(available_commodities)
    if unknown:
        print(f"warning: no data for commodity/commodities: {', '.join(sorted(unknown))}", file=sys.stderr)
    return sorted(c for c in available_commodities if c in wanted_commodities)


def gather_report_data(journal_file, query, commodities):
    """Fetch and group per-commodity rows, and accumulate grand totals by currency."""
    cost_sums = defaultdict(Decimal)
    value_sums = defaultdict(Decimal)
    groups = []
    all_account_rows = []
    for commodity in commodities:
        account_rows, total_row, cost_total_row, value_total_row = commodity_rows(journal_file, query, commodity)
        all_account_rows.extend(account_rows)
        groups.append(text_group(commodity, account_rows, total_row, cost_total_row, value_total_row))
        if cost_total_row is not None:
            amount, currency = parse_amount(cost_total_row)
            cost_sums[currency] += amount
        if value_total_row is not None:
            amount, currency = parse_amount(value_total_row)
            value_sums[currency] += amount
    return groups, all_account_rows, cost_sums, value_sums


def main():
    argv = sys.argv[1:]
    if "-h" in argv or "--help" in argv:
        print(__doc__.strip())
        return

    args = parse_args(argv)
    available_commodities = commodities_in(args.journal_file, args.query)
    commodities = resolve_commodities(available_commodities, args.wanted_commodities)
    groups, all_account_rows, cost_sums, value_sums = gather_report_data(args.journal_file, args.query, commodities)

    if args.csv_output:
        print_csv(all_account_rows)
    else:
        grand_total_row = ("Total (all commodities):", "", format_sums(cost_sums), format_sums(value_sums))
        print_table(groups, grand_total_row)


if __name__ == "__main__":
    main()
