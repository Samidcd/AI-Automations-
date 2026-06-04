"""Load CSV, Excel, or Google Sheets into a DataFrame."""

import io
import json
import re
import pandas as pd


def load_file(uploaded_file) -> pd.DataFrame:
    name = uploaded_file.name.lower()
    if name.endswith(".csv"):
        return pd.read_csv(uploaded_file, dtype=str)
    elif name.endswith((".xlsx", ".xls")):
        return pd.read_excel(uploaded_file, dtype=str)
    raise ValueError(f"Unsupported file type: {uploaded_file.name}")


def load_gsheet(sheet_url: str, sa_json: str, worksheet_index: int = 0) -> pd.DataFrame:
    import gspread
    from google.oauth2.service_account import Credentials

    creds_dict = json.loads(sa_json)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    gc = gspread.authorize(creds)

    sheet_id = _extract_sheet_id(sheet_url)
    spreadsheet = gc.open_by_key(sheet_id)
    worksheet = spreadsheet.get_worksheet(worksheet_index)
    records = worksheet.get_all_records()
    return pd.DataFrame(records).astype(str)


def _extract_sheet_id(url: str) -> str:
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    if not match:
        raise ValueError("Could not extract sheet ID from URL.")
    return match.group(1)
