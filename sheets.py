import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
import os

load_dotenv()

def upload_to_sheets(df: pd.DataFrame):
    creds_path = os.getenv("GOOGLE_CREDENTIALS_PATH")
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    
    creds = Credentials.from_service_account_file(
        creds_path, 
        scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    )
    client = gspread.authorize(creds)
    sheet = client.open_by_key(sheet_id)
    worksheet = sheet.sheet1
    
    worksheet.clear()
    worksheet.update([df.columns.tolist()] + df.fillna("").values.tolist())
    print(f"Успішно завантажено {len(df)} рядків ✅")