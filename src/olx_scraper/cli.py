"""Command line. Exit code 0 only when the run is done or the export is written."""

import argparse
import logging
import re
import signal
import sys
from pathlib import Path

from olx_scraper import export, scrape
from olx_scraper.browser import open_browser
from olx_scraper.fetch import Client
from olx_scraper.store import StoreError, open_store, single_run

DEFAULT_CATEGORY = "nedvizhimost/kvartiry"


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        return _scrape(args) if args.command == "scrape" else _export(args)
    except (StoreError, export.ExportError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


def _scrape(args: argparse.Namespace) -> int:
    # A plain kill or a scheduler timeout should close the run the same way Ctrl-C does.
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    with single_run(args.db), open_store(args.db) as store, open_browser() as browser:
        if abandoned := store.fail_abandoned():
            logging.warning("closed %d abandoned run(s)", abandoned)
        result = scrape.run(Client(browser), store, args.category, args.pages, args.limit)
        print(f"run {result.run}: {result.listings} listings, {result.gaps} without a price")
        for reason, count in store.gap_reasons(result.run):
            print(f"  {count} x {reason}")
    if result.failure:
        print(f"FAILED: {result.failure}", file=sys.stderr)
        return 1
    return 0


def _export(args: argparse.Namespace) -> int:
    if not args.db.exists():
        raise export.ExportError(f"{args.db} does not exist, run scrape first")
    with open_store(args.db) as store:
        table = export.rows(store, args.what)
    if args.csv:
        export.to_csv(table, args.csv)
    else:
        export.to_sheet(table, export.open_sheet())
    print(f"exported {len(table) - 1} rows")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="olx-scraper")
    commands = parser.add_subparsers(dest="command", required=True)

    scrape_cmd = commands.add_parser("scrape", help="read listings into the database")
    scrape_cmd.add_argument("--pages", type=_positive, default=1, help="search pages (default 1)")
    scrape_cmd.add_argument("--limit", type=_positive, help="stop after this many listings")
    scrape_cmd.add_argument("--category", type=_category, default=DEFAULT_CATEGORY)

    export_cmd = commands.add_parser("export", help="write stored rows to a file or a sheet")
    export_cmd.add_argument("what", choices=sorted(export.QUERIES))
    target = export_cmd.add_mutually_exclusive_group(required=True)
    target.add_argument("--csv", type=Path, metavar="PATH")
    target.add_argument("--sheet", action="store_true", help="first tab of GOOGLE_SHEET_ID")

    for command in (scrape_cmd, export_cmd):
        command.add_argument("--db", type=Path, default=Path("olx.sqlite3"))
    return parser


def _positive(text: str) -> int:
    if not text.isdecimal() or int(text) == 0:
        raise argparse.ArgumentTypeError(f"{text!r} is not a positive number")
    return int(text)


def _category(text: str) -> str:
    # Only category paths: robots.txt disallows /search/ and ?q=.
    if not re.fullmatch(r"nedvizhimost(/[a-z0-9-]+)+", text):
        raise argparse.ArgumentTypeError(f"{text!r} is not a nedvizhimost/... category path")
    return text
