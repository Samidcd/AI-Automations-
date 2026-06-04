"""Google Sheets read/write via gspread (service-account or OAuth)."""

from __future__ import annotations

import json
import pandas as pd
import gspread
from gspread.exceptions import APIError


# ── Column mapping for the dashboard sheet ────────────────────────────────────
SHEET_COLUMNS = [
    "Source",
    "First Name",
    "Last Name",
    "Company",
    "Job Title",
    "Country",
    "Registration Email",
    "Enriched Business Email",
    "LinkedIn url's",
    "(Reg) Phone Number",
    "Enriched Phone Number 1",
    "Enriched Phone Number 2",
    "prospectUuid",
]

# Internal name → sheet column header
INTERNAL_TO_SHEET = {
    "source":                  "Source",
    "first_name":              "First Name",
    "last_name":               "Last Name",
    "company":                 "Company",
    "job_title":               "Job Title",
    "country":                 "Country",
    "registration_email":      "Registration Email",
    "business_email":          "Enriched Business Email",
    "linkedin_url":            "LinkedIn url's",
    "phone":                   "(Reg) Phone Number",
    "enriched_phone_1":        "Enriched Phone Number 1",
    "enriched_phone_2":        "Enriched Phone Number 2",
    "prospect_uuid":           "prospectUuid",
}

SHEET_TO_INTERNAL = {v: k for k, v in INTERNAL_TO_SHEET.items()}


def _client_from_json(service_account_json: str) -> gspread.Client:
    """Build a gspread client from a service-account JSON string."""
    creds_dict = json.loads(service_account_json)
    return gspread.service_account_from_dict(creds_dict)


def read_sheet(sheet_url: str, service_account_json: str, worksheet_index: int = 0) -> pd.DataFrame:
    """
    Pull all rows from a Google Sheet and return a normalised DataFrame.
    Rows where 'Enriched Business Email' is empty are flagged with needs_enrichment=True.
    """
    gc = _client_from_json(service_account_json)
    sh = gc.open_by_url(sheet_url)
    ws = sh.get_worksheet(worksheet_index)

    records = ws.get_all_records(expected_headers=[], value_render_option="UNFORMATTED_VALUE")
    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)

    # Rename to internal names
    rename = {col: SHEET_TO_INTERNAL[col] for col in df.columns if col in SHEET_TO_INTERNAL}
    df = df.rename(columns=rename)

    # Flag rows needing enrichment (missing business email)
    be = df.get("business_email", pd.Series(dtype=str))
    df["needs_enrichment"] = be.isna() | (be.astype(str).str.strip() == "")

    # Preserve original row number (1-based, row 1 = header, so data starts at 2)
    df["_sheet_row"] = range(2, len(df) + 2)

    return df


def write_enriched_column(
    sheet_url: str,
    service_account_json: str,
    df: pd.DataFrame,
    worksheet_index: int = 0,
) -> int:
    """
    Write back only the enriched columns that changed (business_email,
    enriched_phone_1, enriched_phone_2) to avoid touching untouched rows.
    Returns the number of cells updated.
    """
    gc = _client_from_json(service_account_json)
    sh = gc.open_by_url(sheet_url)
    ws = sh.get_worksheet(worksheet_index)

    # Get current header row to find column indices
    headers = ws.row_values(1)

    write_cols = {
        "business_email":   "Enriched Business Email",
        "enriched_phone_1": "Enriched Phone Number 1",
        "enriched_phone_2": "Enriched Phone Number 2",
    }

    updates: list[gspread.Cell] = []

    for internal, sheet_col in write_cols.items():
        if internal not in df.columns:
            continue
        if sheet_col not in headers:
            continue
        col_idx = headers.index(sheet_col) + 1  # 1-based

        for _, row in df.iterrows():
            val = row.get(internal, "")
            if pd.isna(val) or str(val).strip() == "":
                continue
            sheet_row = int(row["_sheet_row"])
            updates.append(gspread.Cell(sheet_row, col_idx, str(val).strip()))

    if updates:
        ws.update_cells(updates, value_input_option="USER_ENTERED")

    return len(updates)


def sheet_to_csv(df: pd.DataFrame) -> bytes:
    """Export the dataframe back to CSV using the original sheet column names."""
    out = df.copy()
    # Drop helper columns
    out = out.drop(columns=[c for c in ["needs_enrichment", "_sheet_row"] if c in out.columns])
    # Rename back to sheet headers
    rename = {k: v for k, v in INTERNAL_TO_SHEET.items() if k in out.columns}
    out = out.rename(columns=rename)
    # Restore original column order where possible
    ordered = [c for c in SHEET_COLUMNS if c in out.columns]
    extra = [c for c in out.columns if c not in ordered]
    out = out[ordered + extra]
    return out.to_csv(index=False).encode("utf-8")
