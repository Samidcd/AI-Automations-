"""Airscale API integration for lead enrichment."""

import time
import requests
import pandas as pd

BASE_URL = "https://api.airscale.io/v1"

# Fields marked True are pre-selected by default
AVAILABLE_ENRICHMENTS = {
    "email":          ("Personal / work email address",          True),
    "business_email": ("Business email (company domain format)", True),
    "phone":          ("Direct dial / mobile number",            True),
    "company_domain": ("Company website domain",                 True),
    "linkedin_url":   ("Personal LinkedIn profile URL",          True),
    "country":        ("Country of the lead",                    True),
    "first_name":     ("First name (if missing)",                True),
    "last_name":      ("Last name / second name (if missing)",   True),
    "job_title":      ("Job title (if missing)",                 True),
    "company":        ("Company name (if missing)",              True),
    "company_size":   ("Headcount range",                        False),
    "company_revenue":("Estimated annual revenue",               False),
    "company_industry":("Industry classification",               False),
    "company_funding":("Funding stage & total raised",           False),
    "company_hq":     ("Headquarters location",                  False),
    "company_linkedin":("Company LinkedIn URL",                  False),
    "job_level":      ("Seniority level (C-Suite, VP, etc.)",    False),
    "job_function":   ("Department / function",                  False),
    "technologies":   ("Tech stack the company uses",            False),
}


def enrich(df: pd.DataFrame, fields: list[str], api_key: str) -> pd.DataFrame:
    """
    Send leads to Airscale for enrichment and return the merged dataframe.
    Uses Airscale's bulk enrichment endpoint.
    """
    if not fields:
        return df

    records = _build_records(df)
    payload = {
        "leads": records,
        "enrichments": fields,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # Submit enrichment job
    resp = requests.post(f"{BASE_URL}/enrich/bulk", json=payload, headers=headers, timeout=60)
    if resp.status_code not in (200, 202):
        raise RuntimeError(
            f"Airscale API error {resp.status_code}: {resp.text[:300]}"
        )

    result = resp.json()

    # If async job, poll until done
    job_id = result.get("job_id")
    if job_id:
        result = _poll_job(job_id, headers)

    enriched_rows = result.get("results", result.get("leads", []))
    if not enriched_rows:
        return df

    enriched_df = pd.DataFrame(enriched_rows)
    # Merge back on index order (Airscale preserves order)
    enriched_df = enriched_df.reset_index(drop=True)
    df = df.reset_index(drop=True)

    for col in enriched_df.columns:
        if col not in df.columns:
            df[col] = enriched_df[col]
        else:
            # Fill blanks in original with enriched values
            mask = df[col].isna() | (df[col].astype(str).str.strip() == "")
            df.loc[mask, col] = enriched_df.loc[mask, col]

    return df


def _build_records(df: pd.DataFrame) -> list[dict]:
    """Convert dataframe rows to Airscale lead objects."""
    records = []
    for _, row in df.iterrows():
        rec: dict = {}
        field_map = {
            "first_name": "firstName",
            "last_name": "lastName",
            "full_name": "fullName",
            "job_title": "jobTitle",
            "company": "company",
            "linkedin_url": "linkedinUrl",
            "email": "email",
            "company_domain": "companyDomain",
            "location": "location",
        }
        for src, dst in field_map.items():
            if src in df.columns and pd.notna(row.get(src)):
                rec[dst] = str(row[src]).strip()
        records.append(rec)
    return records


def _poll_job(job_id: str, headers: dict, max_wait: int = 180) -> dict:
    """Poll Airscale async job until complete."""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        resp = requests.get(f"{BASE_URL}/enrich/jobs/{job_id}", headers=headers, timeout=30)
        data = resp.json()
        status = data.get("status", "")
        if status == "completed":
            return data
        if status == "failed":
            raise RuntimeError(f"Airscale job failed: {data.get('error', 'unknown')}")
        time.sleep(5)
    raise TimeoutError(f"Airscale job {job_id} did not complete within {max_wait}s")
