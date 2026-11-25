"""SQLite storage. Every page and every price is committed as soon as it is read."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path

from olx_scraper.parse import Ad, Price

SCHEMA_VERSION = 1


class StoreError(Exception):
    """The database cannot be used for this run."""


@contextmanager
def open_store(path: Path) -> Iterator["Store"]:
    db = sqlite3.connect(path, isolation_level=None)
    try:
        db.execute("pragma foreign_keys = on")
        _migrate(db)
        yield Store(db)
    finally:
        db.close()


@contextmanager
def single_run(path: Path) -> Iterator[None]:
    """Hold an exclusive lock that the OS drops if this process dies.

    Because of that, whoever holds it knows that any 'running' row belongs to a dead process.
    """
    lock = sqlite3.connect(f"{path}.lock", isolation_level=None, timeout=0)
    try:
        try:
            lock.execute("begin exclusive")
        except sqlite3.OperationalError as error:
            raise StoreError(f"another run is using {path}") from error
        yield
    finally:
        lock.close()


def _migrate(db: sqlite3.Connection) -> None:
    version = db.execute("pragma user_version").fetchone()[0]
    if version == SCHEMA_VERSION:
        return
    if version != 0:
        raise StoreError(f"database schema is v{version}, this code needs v{SCHEMA_VERSION}")
    schema = files("olx_scraper").joinpath("schema.sql").read_text("utf-8")
    db.executescript(f"begin; {schema} pragma user_version = {SCHEMA_VERSION}; commit;")


class Store:
    def __init__(self, db: sqlite3.Connection) -> None:
        self._db = db

    def fail_abandoned(self) -> int:
        """Call only while holding single_run."""
        return self._db.execute(
            "update runs set status = 'failed', reason = 'abandoned', ended_at = ?"
            " where status = 'running'",
            (_now(),),
        ).rowcount

    def start_run(self, category: str, pages: int, limit: int | None) -> int:
        row = self._db.execute(
            "insert into runs (category, pages_asked, ad_limit, started_at)"
            " values (?, ?, ?, ?) returning id",
            (category, pages, limit, _now()),
        ).fetchone()
        return int(row[0])

    def save_page(self, run: int, page: int, site_pages: int, ads: list[Ad]) -> int:
        """Returns how many ads are new to this run; a repeat keeps its first position."""
        self._db.execute("begin")
        try:
            before = self._count(run)
            self._db.executemany(
                "insert into observations (run_id, listing_id, seen_at, page, position, promoted,"
                " url, title, deal_type, region, city, district, rooms, floor, total_floors,"
                " area_m2, posted_at) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
                " on conflict (run_id, listing_id) do nothing",
                [_row(run, page, position, ad) for position, ad in enumerate(ads, 1)],
            )
            self._db.execute(
                "update runs set pages_read = pages_read + 1, site_pages = ? where id = ?",
                (site_pages, run),
            )
            new = self._count(run) - before
        except BaseException:
            self._db.execute("rollback")
            raise
        self._db.execute("commit")
        return new

    def unpriced(self, run: int) -> list[tuple[int, str]]:
        return self._db.execute(
            "select listing_id, url from observations o where run_id = ? and price_kind is null"
            " and not exists (select 1 from gaps g where g.run_id = o.run_id"
            " and g.listing_id = o.listing_id) order by page, position",
            (run,),
        ).fetchall()

    def save_price(self, run: int, listing: int, price: Price) -> None:
        self._db.execute(
            "update observations set price_kind = ?, price_cents = ?, currency = ?"
            " where run_id = ? and listing_id = ?",
            (price.kind, price.cents, price.currency, run, listing),
        )

    def save_gap(self, run: int, listing: int, reason: str) -> None:
        self._db.execute("insert into gaps values (?, ?, ?)", (run, listing, reason))

    def end_run(self, run: int, failure: str | None) -> None:
        if failure is None and (left := self.unpriced(run)):
            raise StoreError(f"{len(left)} listings have neither a price nor a named gap")
        self._db.execute(
            "update runs set status = ?, reason = ?, ended_at = ? where id = ?",
            ("done" if failure is None else "failed", failure, _now(), run),
        )

    def counts(self, run: int) -> tuple[int, int]:
        gaps = self._db.execute("select count(*) from gaps where run_id = ?", (run,)).fetchone()[0]
        return self._count(run), int(gaps)

    def gap_reasons(self, run: int) -> list[tuple[str, int]]:
        return self._db.execute(
            "select reason, count(*) from gaps where run_id = ? group by 1 order by 2 desc, 1",
            (run,),
        ).fetchall()

    def table(self, query: str) -> list[list[object]]:
        """Header row, then data rows."""
        cursor = self._db.execute(query)
        return [[c[0] for c in cursor.description], *(list(row) for row in cursor)]

    def _count(self, run: int) -> int:
        row = self._db.execute("select count(*) from observations where run_id = ?", (run,))
        return int(row.fetchone()[0])


def _row(run: int, page: int, position: int, ad: Ad) -> tuple[object, ...]:
    return (
        *(run, ad.id, _now(), page, position, int(ad.promoted), ad.url, ad.title, ad.deal_type),
        *(ad.region, ad.city, ad.district, ad.rooms, ad.floor, ad.total_floors, ad.area_m2),
        ad.posted_at,
    )


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
