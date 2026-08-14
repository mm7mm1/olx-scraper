import logging
import os

import gspread
import pandas as pd
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

load_dotenv()

logger = logging.getLogger(__name__)


def upload_to_sheets(df: pd.DataFrame):
    creds_path = os.getenv("GOOGLE_CREDENTIALS_PATH")
    sheet_id = os.getenv("GOOGLE_SHEET_ID")

    if not creds_path or not sheet_id:
        raise RuntimeError(
            "Задайте GOOGLE_CREDENTIALS_PATH і GOOGLE_SHEET_ID у файлі .env "
            "(див. .env.example)."
        )
    if not os.path.isfile(creds_path):
        raise RuntimeError(f"Файл credentials не знайдено: {creds_path}")

    creds = Credentials.from_service_account_file(
        creds_path,
        scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    )
    client = gspread.authorize(creds)
    sheet = client.open_by_key(sheet_id)
    worksheet = sheet.sheet1

    worksheet.clear()
    worksheet.update([df.columns.tolist()] + df.fillna("").values.tolist())
    logger.info("Успішно завантажено %d рядків ✅", len(df))
