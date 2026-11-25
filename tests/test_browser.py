"""Real Chromium against a local server: the parts a fake transport cannot prove."""

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from olx_scraper.browser import open_browser
from olx_scraper.fetch import NetworkError, Reply

pytestmark = pytest.mark.browser


class Handler(BaseHTTPRequestHandler):
    asked: list[str]

    def do_GET(self) -> None:
        self.asked.append(self.path)
        status = {"/moved": 301, "/blocked": 403, "/slow-down": 429}.get(self.path, 200)
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        if status == 301:
            self.send_header("Location", "/page")
        if status == 429:
            self.send_header("Retry-After", "17")
        self.end_headers()
        self.wfile.write('<p>квартира</p><img src="/photo.png"><script src="/t.js">'.encode())

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def site() -> Iterator[str]:
    Handler.asked = []
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    thread.join()
    server.server_close()


def test_browser_replies(site: str) -> None:
    with open_browser() as browser:
        page = browser.get(f"{site}/page")
        assert page.status == 200
        assert "квартира" in page.text
        assert browser.get(f"{site}/moved") == Reply(301)
        assert browser.get(f"{site}/blocked").status == 403
        assert browser.get(f"{site}/slow-down").retry_after == "17"
        with pytest.raises(NetworkError):
            browser.get("http://127.0.0.1:1/")
    assert not [path for path in Handler.asked if path in ("/photo.png", "/t.js")]
