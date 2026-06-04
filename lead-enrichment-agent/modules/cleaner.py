"""Data cleaning and column standardization."""

import re
import pandas as pd


COLUMN_ORDER = [
    # Core identity — always first
    "first_name",
    "last_name",
    "full_name",
    "job_title",
    "company",
    "country",
    # Primary contact data
    "email",
    "business_email",
    "phone",
    "linkedin_url",
    "company_domain",
    # Secondary company data
    "company_size",
    "company_revenue",
    "company_industry",
    "company_funding",
    "company_hq",
    "company_linkedin",
    # Role detail
    "job_level",
    "job_function",
    # Extras
    "location",
    "industry",
    "technologies",
    "connections",
]


def clean(
    df: pd.DataFrame,
    drop_missing_email: bool = False,
    drop_missing_phone: bool = False,
    dedupe_on: list[str] | None = None,
    title_case_names: bool = True,
    strip_whitespace: bool = True,
) -> pd.DataFrame:
    """Apply cleaning rules to the enriched dataframe."""

    if strip_whitespace:
        str_cols = df.select_dtypes(include="object").columns
        df[str_cols] = df[str_cols].apply(lambda c: c.str.strip())

    if title_case_names:
        for col in ("full_name", "first_name", "last_name"):
            if col in df.columns:
                df[col] = df[col].str.title()

    if drop_missing_email and "email" in df.columns:
        df = df[df["email"].notna() & (df["email"].str.strip() != "")]

    if drop_missing_phone and "phone" in df.columns:
        df = df[df["phone"].notna() & (df["phone"].str.strip() != "")]

    if dedupe_on:
        valid_cols = [c for c in dedupe_on if c in df.columns]
        if valid_cols:
            df = df.drop_duplicates(subset=valid_cols, keep="first")

    # Normalize email to lowercase
    if "email" in df.columns:
        df["email"] = df["email"].str.lower()

    # Normalize LinkedIn URLs
    if "linkedin_url" in df.columns:
        df["linkedin_url"] = df["linkedin_url"].apply(_normalize_linkedin_url)

    # Reorder columns: known order first, then any extras
    ordered = [c for c in COLUMN_ORDER if c in df.columns]
    extras = [c for c in df.columns if c not in ordered]
    df = df[ordered + extras]

    df = df.reset_index(drop=True)
    return df


def segment(df: pd.DataFrame, segment_by: str) -> dict[str, pd.DataFrame]:
    """
    Split the dataframe into groups by a column value.
    Returns a dict of {group_value: sub_dataframe}.
    """
    if segment_by not in df.columns:
        raise ValueError(f"Column '{segment_by}' not found in data.")

    groups = {}
    for value, sub_df in df.groupby(segment_by, dropna=False):
        key = str(value).strip() if pd.notna(value) else "Unknown"
        groups[key] = sub_df.reset_index(drop=True)
    return groups


def _normalize_linkedin_url(url) -> str:
    if pd.isna(url) or str(url).strip() == "":
        return ""
    url = str(url).strip()
    if not url.startswith("http"):
        url = "https://" + url
    # Strip tracking params
    url = re.sub(r"\?.*$", "", url)
    return url.rstrip("/")
