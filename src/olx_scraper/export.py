"""Stored rows to CSV or Google Sheets."""

import csv
import os
from pathlib import Path
from typing import Any, Protocol

from olx_scraper.store import Store

QUERIES = {
    "listings": """
        select o.listing_id, o.url, o.title, o.deal_type, o.price_kind,
               o.price_cents / 100.0 as price, o.currency,
               case when o.area_m2 > 0 then round(o.price_cents / 100.0 / o.area_m2, 1) end
                   as price_per_m2,
               o.region, o.city, o.district, o.rooms, o.floor, o.total_floors, o.area_m2,
               o.promoted, o.posted_at, o.seen_at, g.reason as gap
        from observations o
        left join gaps g using (run_id, listing_id)
        where o.run_id = (select max(id) from runs where status = 'done')
        order by o.page, o.position""",
    "price-changes": "select * from price_changes order by seen_at desc, listing_id",
}


class ExportError(Exception):
    """Nothing was exported."""


class Worksheet(Protocol):
    @property
    def row_count(self) -> int: ...
    @property
    def col_count(self) -> int: ...
    def resize(self, rows: int | None = None, cols: int | None = None) -> Any: ...
    def update(
        self, values: Any, range_name: Any = None, *, value_input_option: Any = None
    ) -> Any: ...


def rows(store: Store, what: str) -> list[list[object]]:
    table = store.table(QUERIES[what])
    if what == "listings" and len(table) == 1:
        raise ExportError("no finished run to export")
    return table


def to_csv(table: list[list[object]], path: Path) -> None:
    # Written next to the target and swapped in, so a crash never leaves half a file.
    draft = path.with_name(f"{path.name}.tmp")
    with draft.open("w", encoding="utf-8", newline="") as file:
        csv.writer(file).writerows(table)
    draft.replace(path)


def to_sheet(table: list[list[object]], sheet: Worksheet) -> None:
    """Overwrite in one call, then trim. If the write fails, the old rows are still there."""
    height, width = len(table), len(table[0])
    sheet.resize(max(height, sheet.row_count), max(width, sheet.col_count))
    values = [["" if cell is None else cell for cell in row] for row in table]
    # RAW: a listing title that starts with "=" must stay text, not become a formula.
    sheet.update(values, "A1", value_input_option="RAW")
    sheet.resize(height, width)


def open_sheet() -> Worksheet:
    path, sheet_id = os.getenv("GOOGLE_CREDENTIALS_PATH"), os.getenv("GOOGLE_SHEET_ID")
    if not path or not sheet_id:
        raise ExportError("set GOOGLE_CREDENTIALS_PATH and GOOGLE_SHEET_ID")
    try:
        import gspread
    except ImportError as error:
        raise ExportError("install the Sheets extra: uv sync --extra sheets") from error
    sheet: Worksheet = gspread.service_account(filename=path).open_by_key(sheet_id).sheet1
    return sheet
