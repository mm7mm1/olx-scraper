from collections.abc import Iterator
from pathlib import Path

import pytest

from olx_scraper import scrape
from olx_scraper.fetch import Reply
from olx_scraper.store import Store, open_store
from tests import kit

CATEGORY = "nedvizhimost/kvartiry"


@pytest.fixture
def store(tmp_path: Path) -> Iterator[Store]:
    with open_store(tmp_path / "olx.sqlite3") as opened:
        yield opened


def scrape_once(
    olx: kit.Olx, store: Store, pages: int = 1, limit: int | None = None
) -> scrape.Result:
    return scrape.run(olx.client(), store, CATEGORY, pages, limit)


def status(store: Store) -> tuple[object, ...]:
    return tuple(store.table("select status, reason from runs order by id desc limit 1")[1])


def test_run_reads_every_price(store: Store) -> None:
    result = scrape_once(kit.Olx([kit.search_html([1, 2, 3])]), store)
    assert (result.listings, result.gaps, result.failure) == (3, 0, None)
    assert status(store) == ("done", None)
    assert store.table("select distinct price_cents, currency from observations")[1:] == [
        [5_990_000, "USD"]
    ]


def test_removed_ad_is_a_named_gap_not_a_lost_row(store: Store) -> None:
    ids = list(range(1, 11))
    result = scrape_once(kit.Olx([kit.search_html(ids)], {4: 410}), store)
    assert (result.listings, result.gaps, result.failure) == (10, 1, None)
    assert store.gap_reasons(result.run) == [("GoneError: HTTP 410", 1)]
    assert store.table("select price_kind from observations where listing_id = 4")[1] == [None]


def test_empty_result_is_a_failure(store: Store) -> None:
    assert scrape_once(kit.Olx([kit.search_html([])]), store).failure == "no listings read"
    assert status(store) == ("failed", "no listings read")


def test_too_many_gaps_is_a_failure(store: Store) -> None:
    ids = list(range(1, 11))
    result = scrape_once(kit.Olx([kit.search_html(ids)], {1: 404, 4: 404, 8: 404}), store)
    assert result.failure == "3 of 10 listings have no readable price"


def test_changed_layout_stops_after_five_ads_in_a_row(store: Store) -> None:
    ids = list(range(1, 51))
    olx = kit.Olx([kit.search_html(ids)], dict.fromkeys(ids, "<html>new design</html>"))
    result = scrape_once(olx, store)
    assert result.failure is not None
    assert "5 unreadable ad pages in a row" in result.failure
    assert len(olx.requests) == 1 + 5
    assert result.gaps == 50


def test_block_stops_the_run_and_keeps_what_was_read(store: Store) -> None:
    olx = kit.Olx([kit.search_html([1, 2, 3, 4])], {3: 403})
    result = scrape_once(olx, store)
    assert result.failure == "ad page: HTTP 403"
    assert len(olx.requests) == 1 + 3
    priced = store.table("select listing_id from observations where price_kind = 'fixed'")[1:]
    assert priced == [[1], [2]]
    assert store.gap_reasons(result.run) == [("not read: ad page: HTTP 403", 2)]


def test_interrupt_closes_the_run(store: Store) -> None:
    def ctrl_c() -> Reply:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        scrape_once(kit.Olx([kit.search_html([1, 2])], {2: ctrl_c}), store)
    assert status(store) == ("failed", "interrupted")
    assert store.unpriced(1) == []


def test_unexpected_error_is_recorded_and_raised(store: Store) -> None:
    def bug() -> Reply:
        raise ZeroDivisionError("oops")

    with pytest.raises(ZeroDivisionError):
        scrape_once(kit.Olx([kit.search_html([1])], {1: bug}), store)
    assert status(store) == ("failed", "ZeroDivisionError: oops")


def test_ad_that_moves_between_pages_is_stored_once(store: Store) -> None:
    pages = [kit.search_html([1, 2], 1, 2), kit.search_html([2, 3], 2, 2)]
    result = scrape_once(kit.Olx(pages), store, pages=2)
    assert result.listings == 3
    assert store.table("select page from observations where listing_id = 2")[1:] == [[1]]


def test_stops_at_the_last_page_the_site_has(store: Store) -> None:
    olx = kit.Olx([kit.search_html([1], 1, 2), kit.search_html([2], 2, 2)])
    assert scrape_once(olx, store, pages=10).failure is None
    assert store.table("select pages_asked, pages_read, site_pages from runs")[1] == [10, 2, 2]


def test_wrong_page_number_is_a_failure(store: Store) -> None:
    olx = kit.Olx([kit.search_html([1], 1, 5), kit.search_html([1], 1, 5)])
    result = scrape_once(olx, store, pages=2)
    assert result.failure == "search page 2: OLX returned page 1"


def test_limit(store: Store) -> None:
    pages = [kit.search_html([1, 2], 1, 3), kit.search_html([3, 4], 2, 3)]
    olx = kit.Olx(pages)
    assert scrape_once(olx, store, pages=3, limit=3).listings == 3
    assert len(olx.requests) == 2 + 3
