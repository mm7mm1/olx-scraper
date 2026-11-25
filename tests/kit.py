"""Fake OLX: recorded page structure served in place of the browser."""

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from olx_scraper.fetch import Client, Reply

FIXTURES = Path(__file__).parent / "fixtures"


def state(name: str) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((FIXTURES / f"{name}.json").read_text("utf-8"))
    return loaded


def html(page_state: object) -> str:
    literal = json.dumps(json.dumps(page_state, ensure_ascii=False))
    return f"<html><script>window.__PRERENDERED_STATE__= {literal};</script></html>"


def search_html(ids: list[int], number: int = 1, total_pages: int = 1) -> str:
    page = state("search")
    listing = page["listing"]["listing"]
    template = listing["ads"][0]
    listing["pageNumber"], listing["totalPages"] = number - 1, total_pages
    listing["ads"] = []
    for listing_id in ids:
        ad = copy.deepcopy(template)
        ad["id"] = listing_id
        ad["url"] = f"https://www.olx.ua/d/uk/obyavlenie/kvartira-{listing_id}.html"
        listing["ads"].append(ad)
    return html(page)


def ad_html(listing_id: int, label: str | None = "59 900 $", **price: object) -> str:
    page = state("ad_usd")
    ad = page["ad"]["ad"]
    ad["id"] = listing_id
    ad["price"] |= {"displayValue": label, **price}
    return html(page)


Answer = str | int | Callable[[], Reply]


class Olx:
    """Answers by path; unknown ads get a good page."""

    def __init__(self, pages: list[str], ads: dict[int, Answer] | None = None) -> None:
        self.pages = pages
        self.ads = ads or {}
        self.requests: list[str] = []

    def client(self) -> Client:
        return Client(self, sleep=lambda _: None)

    def get(self, url: str) -> Reply:
        self.requests.append(url)
        parts = urlsplit(url)
        assert parts.netloc == "www.olx.ua"
        if "/d/uk/obyavlenie/" in parts.path:
            listing_id = int(parts.path.rsplit("-", 1)[1].removesuffix(".html"))
            return _reply(self.ads.get(listing_id, ad_html(listing_id)))
        return _reply(self.pages[int(parse_qs(parts.query).get("page", ["1"])[0]) - 1])


def _reply(answer: Answer) -> Reply:
    if callable(answer):
        return answer()
    if isinstance(answer, int):
        return Reply(answer)
    return Reply(200, answer)
