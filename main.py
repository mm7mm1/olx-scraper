import argparse
import asyncio
import logging

from scraper import run_scraper
from sheets import upload_to_sheets

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description="Скрапер квартир з OLX.ua")
    parser.add_argument("--pages", type=int, default=1, help="кількість сторінок каталогу (default: 1)")
    parser.add_argument("--limit", type=int, default=None, help="максимум оголошень для парсингу")
    parser.add_argument("--csv", default="listings.csv", help="куди зберегти CSV (default: listings.csv)")
    parser.add_argument("--no-upload", action="store_true", help="не завантажувати в Google Sheets")
    return parser.parse_args()


async def main():
    args = parse_args()
    df = await run_scraper(pages=args.pages, limit=args.limit)

    if df.empty:
        logger.warning("Дані не зібрано.")
        return

    # CSV — резервна копія на випадок збою завантаження в Sheets
    df.to_csv(args.csv, index=False)
    logger.info("Збережено %d рядків у %s", len(df), args.csv)

    if not args.no_upload:
        logger.info("Завантаження в Google Sheets...")
        upload_to_sheets(df)
    logger.info("--- ГОТОВО ---")


if __name__ == "__main__":
    asyncio.run(main())
