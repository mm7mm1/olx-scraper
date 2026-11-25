"""OLX pages to typed rows. Pure functions: no network, no storage.

OLX renders its pages on the server and embeds the data as JSON in __PRERENDERED_STATE__,
so nothing here depends on CSS classes or on a browser.
"""

import json
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

_STATE = re.compile(r'__PRERENDERED_STATE__\s*=\s*("(?:[^"\\]|\\.)*")', re.S)
_PRICE = re.compile(r"([\d\s]+(?:\.\d{1,2})?)\s*(грн\.?|\$|€)")
_CURRENCIES = {"грн": "UAH", "$": "USD", "€": "EUR"}
_LEADING_INT = re.compile(r"\d+")


class LayoutError(Exception):
    """The page does not have the shape this parser was written for."""


class UnreadablePriceError(Exception):
    """The price label is there but is not one of the known formats."""


@dataclass(frozen=True, slots=True)
class Ad:
    id: int
    url: str
    title: str
    deal_type: str | None
    region: str | None
    city: str | None
    district: str | None
    rooms: int | None
    floor: int | None
    total_floors: int | None
    area_m2: float | None
    promoted: bool
    posted_at: str | None


@dataclass(frozen=True, slots=True)
class SearchPage:
    number: int
    total_pages: int
    ads: tuple[Ad, ...]


@dataclass(frozen=True, slots=True)
class Price:
    kind: str  # fixed | free | exchange
    cents: int | None = None
    currency: str | None = None


def search_page(html: str) -> SearchPage:
    state = _state(html)
    try:
        listing = state["listing"]["listing"]
        categories = state["categories"]["list"]
        return SearchPage(
            number=listing["pageNumber"] + 1,
            total_pages=listing["totalPages"],
            ads=tuple(_ad(raw, categories) for raw in listing["ads"]),
        )
    except (AttributeError, KeyError, TypeError) as error:
        raise LayoutError(f"search page: missing {error}") from error


def ad_price(html: str, expected_id: int) -> Price:
    """The price in the currency the seller typed.

    Search results and JSON-LD convert every price to one currency, so a USD price stored from
    there would appear to change daily with the exchange rate. Only the label on the ad's own
    page keeps the original.
    """
    state = _state(html)
    try:
        ad = state["ad"]["ad"]
        found, price = ad["id"], ad["price"]
        label, free, exchange = price["displayValue"], price["free"], price["exchange"]
    except (KeyError, TypeError) as error:
        raise LayoutError(f"ad page: missing {error}") from error
    if found != expected_id:
        raise LayoutError(f"ad page: asked for {expected_id}, got {found}")
    if free:
        return Price("free")
    if exchange:
        return Price("exchange")
    return _fixed_price(label)


def _fixed_price(label: str | None) -> Price:
    match = _PRICE.fullmatch((label or "").strip())
    if match is None:
        raise UnreadablePriceError(repr(label))
    amount = Decimal(re.sub(r"\s", "", match[1]))
    return Price("fixed", int(amount * 100), _CURRENCIES[match[2].rstrip(".")])


def _state(html: str) -> dict[str, Any]:
    match = _STATE.search(html)
    if match is None:
        raise LayoutError("no embedded state")
    try:
        state = json.loads(json.loads(match[1]))
    except json.JSONDecodeError as error:
        raise LayoutError(f"embedded state is not JSON: {error}") from error
    if not isinstance(state, dict):
        raise LayoutError("embedded state is not an object")
    return state


def _ad(raw: dict[str, Any], categories: dict[str, Any]) -> Ad:
    params = {p["key"]: p for p in raw["params"]}
    location = raw["location"]
    return Ad(
        id=raw["id"],
        url=raw["url"].split("?")[0],
        title=raw["title"],
        deal_type=_deal_type(categories[str(raw["category"]["id"])]["label"]),
        region=location["regionName"],
        city=location["cityName"],
        district=location["districtName"],
        rooms=_int(params, "number_of_rooms_string"),
        floor=_int(params, "floor"),
        total_floors=_int(params, "total_floors"),
        area_m2=_float(params, "total_area"),
        promoted=raw["searchReason"] == "promoted",
        posted_at=raw["createdTime"],
    )


def _deal_type(category_label: str) -> str | None:
    if category_label.startswith("prodazha"):
        return "sale"
    if "posutochn" in category_label:
        return "rent_daily"
    if "arenda" in category_label:
        return "rent_long"
    return None


def _int(params: dict[str, Any], key: str) -> int | None:
    match = _LEADING_INT.match(str(params[key]["value"])) if key in params else None
    return int(match[0]) if match else None


def _float(params: dict[str, Any], key: str) -> float | None:
    try:
        return float(params[key]["normalizedValue"])
    except (KeyError, TypeError, ValueError):
        return None
