import csv
from pathlib import Path
from typing import Any

import pytest

from olx_scraper import export, scrape
from olx_scraper.store import open_store
from tests import kit


class Sheet:
    def __init__(self, rows: int, cols: int, fails: bool = False) -> None:
        self.row_count, self.col_count, self.fails = rows, cols, fails
        self.written: list[list[object]] | None = None
        self.option: str | None = None

    def resize(self, rows: int | None = None, cols: int | None = None) -> None:
        self.row_count, self.col_count = rows or self.row_count, cols or self.col_count

    def update(
        self, values: Any, range_name: Any = None, *, value_input_option: Any = None
    ) -> None:
        if self.fails:
            raise ConnectionError
        self.written, self.option = values, value_input_option


def test_sheet_is_overwritten_then_trimmed() -> None:
    sheet = Sheet(rows=100, cols=26)
    export.to_sheet([["a", "b"], [1, None]], sheet)
    assert sheet.written == [["a", "b"], [1, ""]]
    assert (sheet.row_count, sheet.col_count) == (2, 2)
    assert sheet.option == "RAW"


def test_failed_write_leaves_the_old_rows() -> None:
    sheet = Sheet(rows=100, cols=26, fails=True)
    with pytest.raises(ConnectionError):
        export.to_sheet([["a"], [1]], sheet)
    assert (sheet.row_count, sheet.col_count) == (100, 26)


def test_listings_to_csv(tmp_path: Path) -> None:
    with open_store(tmp_path / "db") as store:
        with pytest.raises(export.ExportError, match="no finished run"):
            export.rows(store, "listings")
        client = kit.Olx([kit.search_html([1, 2])]).client()
        scrape.run(client, store, "nedvizhimost/kvartiry", 1, None)
        export.to_csv(export.rows(store, "listings"), tmp_path / "out.csv")
    with (tmp_path / "out.csv").open(encoding="utf-8", newline="") as file:
        first, second = csv.DictReader(file)
    assert (first["price"], first["currency"], first["gap"]) == ("59900.0", "USD", "")
    assert float(first["price_per_m2"]) == round(59900 / float(first["area_m2"]), 1)
    assert second["listing_id"] == "2"
    assert [p.name for p in tmp_path.glob("*.tmp")] == []
