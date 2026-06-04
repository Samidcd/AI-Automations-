"""Lead file parsing — supports CSV and Excel exports from any source."""

import pandas as pd


COLUMN_MAP = {
    # Standard LinkedIn / Sales Nav columns
    "First Name": "first_name",
    "Last Name": "last_name",
    "Full Name": "full_name",
    "Title": "job_title",
    "Job Title": "job_title",
    "Company": "company",
    "Company Name": "company",
    "LinkedIn URL": "linkedin_url",
    "Profile URL": "linkedin_url",
    "LinkedIn Profile URL": "linkedin_url",
    "LinkedIn url's": "linkedin_url",
    "Location": "location",
    "Geography": "location",
    "Industry": "industry",
    "Connections": "connections",
    "Email": "email",
    "Business Email": "business_email",
    "Work Email": "business_email",
    "Enriched Business Email": "business_email",
    "Registration Email": "registration_email",
    "Phone": "phone",
    "Phone Number": "phone",
    "(Reg) Phone Number": "phone",
    "Enriched Phone Number 1": "enriched_phone_1",
    "Enriched Phone Number 2": "enriched_phone_2",
    "Country": "country",
    "Country/Region": "country",
    "Source": "source",
    "prospectUuid": "prospect_uuid",
}


def parse_file(uploaded_file) -> pd.DataFrame:
    """Parse an uploaded CSV or Excel leads export."""
    name = uploaded_file.name.lower()
    if name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    elif name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(uploaded_file)
    else:
        raise ValueError(f"Unsupported file type: {uploaded_file.name}")

    return _normalize_columns(df)


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename known column headers to internal standard names."""
    rename = {}
    for col in df.columns:
        col_stripped = col.strip()
        if col_stripped in COLUMN_MAP:
            rename[col] = COLUMN_MAP[col_stripped]
    df = df.rename(columns=rename)
    if "full_name" not in df.columns:
        fn = df.get("first_name", pd.Series(dtype=str)).fillna("")
        ln = df.get("last_name", pd.Series(dtype=str)).fillna("")
        df["full_name"] = (fn + " " + ln).str.strip()
    return df
