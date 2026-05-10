import asyncio
from scraper import run_scraper
from sheets import upload_to_sheets

async def main():
    
    PAGES = 1
    LIMIT = None 
    
    df = await run_scraper(pages=PAGES, limit=LIMIT)
    
    if not df.empty:
        print("Завантаження в Google Sheets...")
        upload_to_sheets(df)
        print("--- ГОТОВО ---")
    else:
        print("Дані не зібрано.")

if __name__ == "__main__":
    asyncio.run(main())