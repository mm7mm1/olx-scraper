import asyncio
import logging
import re
from datetime import datetime, timezone

import pandas as pd
from playwright.async_api import async_playwright

BASE_URL = "https://www.olx.ua/uk/nedvizhimost/kvartiry/"
CONCURRENCY = 5
RETRIES = 2

logger = logging.getLogger(__name__)


def extract_int(text):
    if not text: return None
    m = re.search(r"\d+", text.replace(" ", "").replace("\xa0", ""))
    return int(m.group()) if m else None


def extract_float(text):
    if not text: return None
    m = re.search(r"[\d.,]+", text)
    return float(m.group().replace(",", ".")) if m else None


def find_param(params, prefix):
    prefix = prefix.lower()
    return next((p for p in params if p.lower().startswith(prefix)), None)


def deal_type_from_category(category_url):
    if not category_url: return None
    if "posutochno" in category_url: return "подобова оренда"
    if "arenda" in category_url: return "довгострокова оренда"
    if "prodazha" in category_url: return "продаж"
    return None


def currency_from_text(price_text):
    if "грн" in price_text: return "UAH"
    if "$" in price_text: return "USD"
    if "€" in price_text: return "EUR"
    return None


async def get_listing_urls(page, num_pages=1):
    urls = []
    seen = set()
    for i in range(1, num_pages + 1):
        url = BASE_URL if i == 1 else f"{BASE_URL}?page={i}"
        await page.goto(url, timeout=60000)
        await page.wait_for_selector("[data-testid='l-card']")

        hrefs = await page.eval_on_selector_all(
            "[data-testid='l-card'] a[href*='/d/uk/']",
            "elements => elements.map(e => e.href)"
        )
        new_on_page = 0
        for href in hrefs:
            clean = href.split("?")[0]
            if clean not in seen:
                seen.add(clean)
                urls.append(clean)
                new_on_page += 1

        # OLX віддає першу сторінку для неіснуючих ?page=N — зупиняємось, коли нових URL немає
        if new_on_page == 0:
            logger.info("Сторінка %d не дала нових оголошень — зупиняю пагінацію.", i)
            break
    return urls


async def _extract_listing_data(page, url):
    await page.goto(url, timeout=60000)
    await page.wait_for_selector("[data-testid='ad-price-container']", timeout=10000)

    data = await page.evaluate("""() => {
        const ld = [...document.querySelectorAll("script[type='application/ld+json']")]
            .map(s => { try { return JSON.parse(s.textContent); } catch { return null; } })
            .find(o => o && o["@type"] === "Product") || null;
        const breadcrumbs = [...document.querySelectorAll("[data-testid='breadcrumb-item']")]
            .map(li => li.innerText.trim());
        const params = [...document.querySelectorAll("[data-testid='ad-parameters-container'] p")]
            .map(p => p.innerText.trim());
        const priceText = document.querySelector("[data-testid='ad-price-container']")?.innerText || "";
        const title = document.querySelector("[data-testid='offer_title']")?.innerText?.trim()
            || document.querySelector("h1")?.innerText?.trim() || "";
        return { ld, breadcrumbs, params, priceText, title };
    }""")

    ld = data["ld"] or {}
    offer = ld.get("offers") or {}
    params = data["params"]
    breadcrumbs = data["breadcrumbs"]

    # Локаційні елементи хлібних крихт ідуть у порядку: область → місто → (район)
    located = [b.split(" - ", 1)[1] for b in breadcrumbs if " - " in b]
    region = located[0] if located else None
    city = located[1] if len(located) >= 2 else region
    district = located[2] if len(located) >= 3 else None
    if not city:
        area_served = offer.get("areaServed") or {}
        city = area_served.get("name")

    price = offer.get("price") or extract_int(data["priceText"])
    return {
        "url": url,
        "title": ld.get("name") or data["title"],
        "deal_type": deal_type_from_category(ld.get("category")),
        "price": price,
        "currency": offer.get("priceCurrency") or currency_from_text(data["priceText"]),
        "city": city,
        "district": district,
        "region": region,
        "rooms": extract_int(find_param(params, "кількість кімнат")),
        "floor": extract_int(find_param(params, "поверх:")),
        "total_floors": extract_int(find_param(params, "поверховість")),
        "area": extract_float(find_param(params, "загальна площа")),
        "scraped_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


async def parse_single_listing(browser_context, url):
    for attempt in range(1, RETRIES + 2):
        page = await browser_context.new_page()
        try:
            return await _extract_listing_data(page, url)
        except Exception as e:
            if attempt <= RETRIES:
                logger.warning("Спроба %d не вдалась для %s: %s — повторюю.", attempt, url, e)
                await asyncio.sleep(2 * attempt)
            else:
                logger.error("Пропускаю %s після %d спроб: %s", url, attempt, e)
                return None
        finally:
            await page.close()


async def run_scraper(pages=1, limit=None):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        logger.info("Збираю посилання...")
        urls = await get_listing_urls(page, pages)
        if limit: urls = urls[:limit]

        logger.info("Парсинг %d оголошень... (чергами по %d)", len(urls), CONCURRENCY)

        semaphore = asyncio.Semaphore(CONCURRENCY)

        async def sem_task(url):
            async with semaphore:
                return await parse_single_listing(context, url)

        results = await asyncio.gather(*(sem_task(url) for url in urls))

        await browser.close()

        df = pd.DataFrame([r for r in results if r])
        if not df.empty:
            df["price_per_m2"] = (df["price"] / df["area"]).round(1)
        return df
