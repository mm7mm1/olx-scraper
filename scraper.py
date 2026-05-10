import asyncio
import re
from playwright.async_api import async_playwright
import pandas as pd

BASE_URL = "https://www.olx.ua/uk/nedvizhimost/kvartiry/"

def extract_int(text):
    if not text: return None
    m = re.search(r"\d+", text.replace(" ", ""))
    return int(m.group()) if m else None

def extract_float(text):
    if not text: return None
    m = re.search(r"[\d.,]+", text)
    return float(m.group().replace(",", ".")) if m else None

async def get_listing_urls(page, num_pages=1):
    urls = set()
    for i in range(1, num_pages + 1):
        url = BASE_URL if i == 1 else f"{BASE_URL}?page={i}"
        await page.goto(url)
        await page.wait_for_selector("[data-testid='l-card']")
        
        hrefs = await page.eval_on_selector_all(
            "a[href*='/d/uk/']", 
            "elements => elements.map(e => e.href)"
        )
        for href in hrefs:
            urls.add(href.split("?")[0])
    return list(urls)

async def parse_single_listing(browser_context, url):
    page = await browser_context.new_page()
    try:
        await page.goto(url, timeout=60000)
        await page.wait_for_selector("[data-testid='ad-price-container']", timeout=10000)

        data = await page.evaluate("""() => {
            const price = document.querySelector("[data-testid='ad-price-container'] h3")?.innerText || "";
            const locElements = document.querySelectorAll("div.css-1r8egxr p");
            const city = locElements[0]?.innerText || "";
            const region = locElements[1]?.innerText || "";
            
            const params = {};
            document.querySelectorAll("p[data-nx-name]").forEach(p => {
                params[p.innerText.toLowerCase()] = p.innerText;
            });

            return { price, city, region, params_list: Object.keys(params).join(" | ") };
        }""")

        return {
            "url": url,
            "price": extract_int(data["price"]),
            "city": data["city"],
            "region": data["region"],
            "floor": extract_int(next((v for v in data["params_list"].split(" | ") if "поверх:" in v.lower()), None)),
            "total_floors": extract_int(next((v for v in data["params_list"].split(" | ") if "поверховість" in v.lower()), None)),
            "area": extract_float(next((v for v in data["params_list"].split(" | ") if "загальна площа" in v.lower()), None)),
        }
    except Exception as e:
        print(f"Помилка на {url}: {e}")
        return None
    finally:
        await page.close()

async def run_scraper(pages=1, limit=None):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        print("Збираю посилання...")
        urls = await get_listing_urls(page, pages)
        if limit: urls = urls[:limit]

        print(f"Парсинг {len(urls)} оголошень... (чергами по 5)")

       
        semaphore = asyncio.Semaphore(5) 

        async def sem_task(url):
            async with semaphore:
                return await parse_single_listing(context, url)

        
        tasks = [sem_task(url) for url in urls]
        results = await asyncio.gather(*tasks)
        # -----------------------

        await browser.close()
        return pd.DataFrame([r for r in results if r])