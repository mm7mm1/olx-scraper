"""One run, start to end: search pages first, then the native price of each ad."""

import logging
from dataclasses import dataclass

from olx_scraper import parse
from olx_scraper.fetch import BlockedError, Client, GoneError, UnavailableError
from olx_scraper.store import Store

MAX_CONSECUTIVE_GAPS = 5  # this many in a row means the site changed, not five bad ads
MAX_GAP_SHARE = 0.2
BASE_URL = "https://www.olx.ua"

log = logging.getLogger(__name__)


class StopRunError(Exception):
    """The run cannot go on; what was read so far stays stored."""


@dataclass(frozen=True, slots=True)
class Result:
    run: int
    listings: int
    gaps: int
    failure: str | None


def run(client: Client, store: Store, category: str, pages: int, limit: int | None) -> Result:
    run_id = store.start_run(category, pages, limit)
    failure: str | None = "interrupted"
    try:
        _search(client, store, run_id, category, pages, limit)
        _prices(client, store, run_id)
        failure = _verdict(*store.counts(run_id))
    except StopRunError as error:
        failure = str(error)
    except Exception as error:
        failure = f"{type(error).__name__}: {error}"
        raise
    finally:
        # Also runs on Ctrl-C, so a stopped run is closed with its gaps named.
        _name_unread(store, run_id, failure)
        store.end_run(run_id, failure)
    return Result(run_id, *store.counts(run_id), failure)


def _search(
    client: Client, store: Store, run_id: int, category: str, pages: int, limit: int | None
) -> None:
    left = limit
    for number in range(1, pages + 1):
        page = _search_page(client, category, number)
        ads = list(page.ads if left is None else page.ads[:left])
        new = store.save_page(run_id, number, page.total_pages, ads)
        log.info("page %d/%d: %d ads, %d new", number, page.total_pages, len(ads), new)
        if left is not None:
            left -= new
        if number >= page.total_pages or left == 0:
            return


def _search_page(client: Client, category: str, number: int) -> parse.SearchPage:
    url = f"{BASE_URL}/uk/{category}/" + (f"?page={number}" if number > 1 else "")
    try:
        page = parse.search_page(client.get(url))
    except (BlockedError, GoneError, UnavailableError, parse.LayoutError) as error:
        raise StopRunError(f"search page {number}: {error}") from error
    if page.number != number:
        raise StopRunError(f"search page {number}: OLX returned page {page.number}")
    return page


def _prices(client: Client, store: Store, run_id: int) -> None:
    in_a_row = 0
    for listing, url in store.unpriced(run_id):
        try:
            store.save_price(run_id, listing, _price(client, listing, url))
        except BlockedError as error:
            raise StopRunError(f"ad page: {error}") from error
        except (UnavailableError, parse.LayoutError, parse.UnreadablePriceError) as error:
            in_a_row += 1
            store.save_gap(run_id, listing, f"{type(error).__name__}: {error}")
            if in_a_row == MAX_CONSECUTIVE_GAPS:
                raise StopRunError(f"{in_a_row} unreadable ad pages in a row: {error}") from error
        except GoneError as error:
            store.save_gap(run_id, listing, f"GoneError: {error}")
        else:
            in_a_row = 0


def _price(client: Client, listing: int, url: str) -> parse.Price:
    return parse.ad_price(client.get(url), listing)


def _verdict(listings: int, gaps: int) -> str | None:
    if listings == 0:
        return "no listings read"
    if gaps / listings > MAX_GAP_SHARE:
        return f"{gaps} of {listings} listings have no readable price"
    return None


def _name_unread(store: Store, run_id: int, failure: str | None) -> None:
    for listing, _ in store.unpriced(run_id) if failure else []:
        store.save_gap(run_id, listing, f"not read: {failure}")
