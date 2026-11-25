import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from olx_scraper.parse import Ad, Price
from olx_scraper.store import Store, StoreError, open_store, single_run

AD = Ad(1, "https://www.olx.ua/1", "A", "sale", "R", "C", None, 1, 2, 9, 40.0, False, None)
TWO_DOLLARS = Price("fixed", 200, "USD")


def observe(store: Store, price: Price | None, seen_at: str) -> None:
    run = store.start_run("c", 1, None)
    if price:
        store.save_page(run, 1, 1, [AD])
        store.save_price(run, AD.id, price)
        store._db.execute("update observations set seen_at = ? where run_id = ?", (seen_at, run))
    store.end_run(run, None)


def test_price_change_is_found_across_a_run_that_missed_the_listing(tmp_path: Path) -> None:
    with open_store(tmp_path / "db") as store:
        observe(store, TWO_DOLLARS, "2026-01-01")
        observe(store, None, "2026-01-02")
        observe(store, Price("fixed", 150, "USD"), "2026-01-03")
        changes = store.table(
            "select price_before, price_after, change_pct, prev_seen_at from price_changes"
        )
    assert changes[1:] == [[2.0, 1.5, -25.0, "2026-01-01"]]


def test_currency_switch_is_not_a_price_change(tmp_path: Path) -> None:
    with open_store(tmp_path / "db") as store:
        observe(store, TWO_DOLLARS, "2026-01-01")
        observe(store, Price("fixed", 9000, "UAH"), "2026-01-02")
        assert store.table("select * from price_changes")[1:] == []


def test_run_cannot_end_done_with_an_unexplained_price(tmp_path: Path) -> None:
    with open_store(tmp_path / "db") as store:
        run = store.start_run("c", 1, None)
        store.save_page(run, 1, 1, [AD])
        with pytest.raises(StoreError, match="neither a price nor a named gap"):
            store.end_run(run, None)
        store.save_gap(run, AD.id, "why")
        store.end_run(run, None)


@pytest.mark.parametrize(
    "price", [Price("fixed"), Price("free", 1, "USD"), Price("fixed", 1), Price("fixed", -1, "USD")]
)
def test_database_rejects_half_a_price(tmp_path: Path, price: Price) -> None:
    with open_store(tmp_path / "db") as store:
        run = store.start_run("c", 1, None)
        store.save_page(run, 1, 1, [AD])
        with pytest.raises(sqlite3.IntegrityError):
            store.save_price(run, AD.id, price)


def test_second_run_is_refused(tmp_path: Path) -> None:
    with (
        single_run(tmp_path / "db"),
        pytest.raises(StoreError, match="another run"),
        single_run(tmp_path / "db"),
    ):
        pass
    with single_run(tmp_path / "db"):
        pass


def test_killed_run_releases_the_lock_and_is_closed(tmp_path: Path) -> None:
    db = tmp_path / "db"
    code = (
        "import os, pathlib, sys\n"
        "from olx_scraper.store import open_store, single_run\n"
        "db = pathlib.Path(sys.argv[1])\n"
        "with single_run(db), open_store(db) as store:\n"
        "    store.start_run('c', 1, None)\n"
        "    os.kill(os.getpid(), 9)\n"
    )
    killed = subprocess.run([sys.executable, "-c", code, str(db)], check=False)  # noqa: S603
    assert killed.returncode == -9
    with single_run(db), open_store(db) as store:
        assert store.fail_abandoned() == 1
        assert store.table("select status, reason from runs")[1:] == [["failed", "abandoned"]]


def test_unknown_schema_version_is_refused(tmp_path: Path) -> None:
    with sqlite3.connect(tmp_path / "db") as db:
        db.execute("pragma user_version = 99")
    db.close()
    with pytest.raises(StoreError, match="v99"), open_store(tmp_path / "db"):
        pass
