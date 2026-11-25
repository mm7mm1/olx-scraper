import pytest

from olx_scraper import parse
from tests import kit


def test_search_page_reads_recorded_structure() -> None:
    page = parse.search_page(kit.html(kit.state("search")))
    assert (page.number, page.total_pages, len(page.ads)) == (1, 25, 5)
    first, *_, last = page.ads
    assert first.id == 1001
    assert first.url == "https://www.olx.ua/d/uk/obyavlenie/kvartira-ID1.html"
    assert (first.deal_type, last.deal_type) == ("sale", "rent_long")
    assert {ad.promoted for ad in page.ads} == {True, False}
    for ad in page.ads:
        assert ad.city
        assert ad.region
        assert ad.rooms
        assert ad.floor is not None
        assert ad.area_m2 is not None
        assert ad.area_m2 > 0


def test_price_is_the_sellers_not_the_converted_one() -> None:
    recorded = kit.state("ad_usd")
    converted = recorded["ad"]["ad"]["price"]["regularPrice"]
    assert (converted["value"], converted["currencyCode"]) == (2717016, "UAH")
    assert parse.ad_price(kit.html(recorded), 1001) == parse.Price("fixed", 5_990_000, "USD")


@pytest.mark.parametrize(
    ("label", "cents", "currency"),
    [
        ("29 999 грн.", 2_999_900, "UAH"),
        ("29 999 грн", 2_999_900, "UAH"),
        ("500 $", 50_000, "USD"),
        ("661.37 $", 66_137, "USD"),
        ("1 000 €", 100_000, "EUR"),
    ],
)
def test_known_price_labels(label: str, cents: int, currency: str) -> None:
    assert parse.ad_price(kit.ad_html(7, label), 7) == parse.Price("fixed", cents, currency)


@pytest.mark.parametrize("label", ["", None, "від 500 $", "500", "Договірна", "~500 $", "500 £"])
def test_unknown_price_label_is_never_guessed(label: str | None) -> None:
    with pytest.raises(parse.UnreadablePriceError):
        parse.ad_price(kit.ad_html(7, label), 7)


@pytest.mark.parametrize("kind", ["free", "exchange"])
def test_ads_without_money_are_not_gaps(kind: str) -> None:
    assert parse.ad_price(kit.ad_html(7, "", **{kind: True}), 7) == parse.Price(kind)


def test_another_ad_in_the_response_is_refused() -> None:
    with pytest.raises(parse.LayoutError, match="asked for 8, got 7"):
        parse.ad_price(kit.ad_html(7), 8)


@pytest.mark.parametrize(
    "html", ["", "<html>captcha</html>", kit.html({}), kit.html([]), kit.html({"listing": None})]
)
def test_unexpected_layout_is_an_error(html: str) -> None:
    with pytest.raises(parse.LayoutError):
        parse.search_page(html)
    with pytest.raises(parse.LayoutError):
        parse.ad_price(html, 1)
