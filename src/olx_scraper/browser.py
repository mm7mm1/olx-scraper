"""A plain headless Chromium as the transport: no stealth plugins, no spoofed identity."""

from collections.abc import Iterator
from contextlib import contextmanager, suppress

from playwright.sync_api import Error, Page, Route, sync_playwright

from olx_scraper.fetch import NetworkError, Reply

TIMEOUT_MS = 30_000


@contextmanager
def open_browser() -> Iterator["Browser"]:
    with sync_playwright() as playwright:
        chromium = playwright.chromium.launch()
        try:
            page = chromium.new_page(locale="uk-UA")
            page.route("**/*", _document_only)
            yield Browser(page)
        finally:
            # After Ctrl-C the browser process may already be gone; that must not hide the reason.
            with suppress(Error):
                chromium.close()


class Browser:
    def __init__(self, page: Page) -> None:
        self._page = page

    def get(self, url: str) -> Reply:
        try:
            response = self._page.goto(url, wait_until="commit", timeout=TIMEOUT_MS)
            if response is None:
                raise NetworkError("no response")
            # A page past the end redirects to the category root, i.e. to page 1 again.
            first = response.request
            while first.redirected_from:
                first = first.redirected_from
            if first is not response.request:
                moved = first.response()
                return Reply(moved.status if moved else 302)
            return Reply(response.status, response.text(), response.headers.get("retry-after", ""))
        except Error as error:
            raise NetworkError(error.message.splitlines()[0]) from error


def _document_only(route: Route) -> None:
    # The data is in the document itself, so scripts, images and trackers are never requested.
    if route.request.resource_type == "document":
        route.continue_()
    else:
        route.abort()
