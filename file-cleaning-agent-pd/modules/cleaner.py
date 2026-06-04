"""Hard cleaning rules for File Cleaning Agent PD."""

import re
import unicodedata
import pandas as pd

# ── Titles and credentials to strip ──────────────────────────────────────────

TITLES = {
    "dr", "dr.", "prof", "prof.", "mr", "mr.", "mrs", "mrs.", "ms", "ms.",
    "miss", "rev", "rev.", "sir", "lord", "lady", "hon", "hon.",
    "eng", "eng.", "capt", "capt.", "col", "col.", "gen", "gen.",
    "lt", "lt.", "sgt", "sgt.", "cpl", "cpl.",
}

CREDENTIALS = {
    "md", "phd", "ph.d", "ph.d.", "mba", "msc", "ms", "ma", "ba", "bs",
    "do", "dds", "dvm", "jd", "rn", "np", "pa", "cnp", "cpa", "cfa",
    "pe", "pmp", "cissp", "ceo", "cto", "coo", "cfo", "cmo",
    "esq", "esq.", "ii", "iii", "iv", "jr", "jr.", "sr", "sr.",
}

# Characters that should never appear in a name field
_NAME_JUNK_RE = re.compile(
    r'[!@#$%^&*()+=\[\]{};\'\\|<>?/~`"]'  # special chars
    r'|(?<!\w)og(?!\w)'                    # standalone "og"
    r'|(?<!\w)OG(?!\w)',                   # standalone "OG"
    re.IGNORECASE,
)

# Emoji pattern
_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F9FF"
    "\U00002600-\U000027BF"
    "\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF"
    "\U00002702-\U000027B0"
    "]+",
    flags=re.UNICODE,
)


def _strip_emojis(text: str) -> str:
    return _EMOJI_RE.sub("", text).strip()


def _remove_junk_chars(text: str) -> str:
    """Remove special characters that don't belong in name fields."""
    return _NAME_JUNK_RE.sub("", text).strip()


def _title_case(text: str) -> str:
    return text.title()


# ── First name ────────────────────────────────────────────────────────────────

def clean_first_name(val) -> str:
    if pd.isna(val) or str(val).strip() == "":
        return ""
    text = str(val).strip()
    text = _strip_emojis(text)
    text = _remove_junk_chars(text)

    # Split on whitespace/comma; take first non-title token
    tokens = re.split(r"[\s,]+", text)
    result_tokens = []
    for tok in tokens:
        tok_clean = tok.strip(".,")
        if tok_clean.lower() in TITLES:
            continue  # drop title prefix
        if tok_clean.lower() in CREDENTIALS:
            break  # stop at credential suffix
        result_tokens.append(tok_clean)
        break  # only first name token

    result = result_tokens[0] if result_tokens else ""
    return _title_case(result)


# ── Last name ─────────────────────────────────────────────────────────────────

def clean_last_name(val) -> str:
    if pd.isna(val) or str(val).strip() == "":
        return ""
    text = str(val).strip()
    text = _strip_emojis(text)
    text = _remove_junk_chars(text)

    # Remove credential suffixes separated by comma or space
    tokens = re.split(r"[\s,]+", text)
    result_tokens = []
    for tok in tokens:
        tok_clean = tok.strip(".,")
        if tok_clean.lower() in CREDENTIALS:
            break
        if tok_clean.lower() in TITLES:
            continue
        result_tokens.append(tok_clean)

    result = " ".join(result_tokens).strip()
    return _title_case(result)


# ── Job title ─────────────────────────────────────────────────────────────────

def clean_job_title(val) -> str:
    if pd.isna(val) or str(val).strip() == "":
        return ""
    text = str(val).strip()
    text = _strip_emojis(text)
    # Remove non-printable/control chars but keep standard punctuation
    text = "".join(ch for ch in text if unicodedata.category(ch)[0] != "C")
    # Collapse multiple spaces
    text = re.sub(r" {2,}", " ", text).strip()
    return text


# ── LinkedIn URL ──────────────────────────────────────────────────────────────

def clean_linkedin_url(val) -> str:
    if pd.isna(val) or str(val).strip() == "":
        return ""
    url = str(val).strip()
    if not url.startswith("http"):
        url = "https://" + url
    url = re.sub(r"\?.*$", "", url)  # strip tracking params
    return url.rstrip("/")


# ── Company name ──────────────────────────────────────────────────────────────

_COMPANY_JUNK_RE = re.compile(
    r'[!@#$%^&*()+=\[\]{};\'\\|<>?/~`"]'
    r'|\s{2,}'
)

def clean_company_name(val) -> str:
    if pd.isna(val) or str(val).strip() == "":
        return ""
    text = str(val).strip()
    text = _strip_emojis(text)
    # Remove junk chars but preserve hyphens that are part of names (e.g. Coca-Cola)
    # Strip leading/trailing hyphens and doubled hyphens
    text = re.sub(r"[!@#$%^&*()+=\[\]{};\'\\|<>?/~`\"]", "", text)
    text = re.sub(r"-{2,}", "-", text)   # double hyphens → single
    text = re.sub(r"(^-+|-+$)", "", text)  # leading/trailing hyphens
    text = "".join(ch for ch in text if unicodedata.category(ch)[0] != "C")
    text = re.sub(r" {2,}", " ", text).strip()
    return text


# ── Location → Country ────────────────────────────────────────────────────────

US_STATES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new hampshire", "new jersey", "new mexico", "new york",
    "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode island", "south carolina", "south dakota",
    "tennessee", "texas", "utah", "vermont", "virginia", "washington",
    "west virginia", "wisconsin", "wyoming", "district of columbia",
    "dc", "d.c.",
}

US_STATE_ABBREVS = {
    "al","ak","az","ar","ca","co","ct","de","fl","ga","hi","id","il","in",
    "ia","ks","ky","la","me","md","ma","mi","mn","ms","mo","mt","ne","nv",
    "nh","nj","nm","ny","nc","nd","oh","ok","or","pa","ri","sc","sd","tn",
    "tx","ut","vt","va","wa","wv","wi","wy","dc",
}

# Map common country name variants to standardized names
COUNTRY_ALIASES: dict[str, str] = {
    "united states": "United States",
    "united states of america": "United States",
    "usa": "United States",
    "u.s.a.": "United States",
    "u.s.": "United States",
    "us": "United States",
    "uk": "United Kingdom",
    "united kingdom": "United Kingdom",
    "great britain": "United Kingdom",
    "england": "United Kingdom",
    "scotland": "United Kingdom",
    "wales": "United Kingdom",
    "northern ireland": "United Kingdom",
    "uae": "United Arab Emirates",
    "u.a.e.": "United Arab Emirates",
    "united arab emirates": "United Arab Emirates",
    "south korea": "South Korea",
    "republic of korea": "South Korea",
    "korea": "South Korea",
    "north korea": "North Korea",
    "dprk": "North Korea",
    "czech republic": "Czech Republic",
    "czechia": "Czech Republic",
    "taiwan": "Taiwan",
    "hong kong": "Hong Kong",
    "singapore": "Singapore",
    "canada": "Canada",
    "australia": "Australia",
    "new zealand": "New Zealand",
    "germany": "Germany",
    "deutschland": "Germany",
    "france": "France",
    "spain": "Spain",
    "españa": "Spain",
    "italy": "Italy",
    "italia": "Italy",
    "netherlands": "Netherlands",
    "the netherlands": "Netherlands",
    "holland": "Netherlands",
    "switzerland": "Switzerland",
    "sweden": "Sweden",
    "norway": "Norway",
    "denmark": "Denmark",
    "finland": "Finland",
    "belgium": "Belgium",
    "austria": "Austria",
    "portugal": "Portugal",
    "poland": "Poland",
    "brazil": "Brazil",
    "brasil": "Brazil",
    "mexico": "Mexico",
    "méxico": "Mexico",
    "argentina": "Argentina",
    "chile": "Chile",
    "colombia": "Colombia",
    "peru": "Peru",
    "india": "India",
    "china": "China",
    "japan": "Japan",
    "indonesia": "Indonesia",
    "malaysia": "Malaysia",
    "philippines": "Philippines",
    "thailand": "Thailand",
    "vietnam": "Vietnam",
    "pakistan": "Pakistan",
    "bangladesh": "Bangladesh",
    "nigeria": "Nigeria",
    "south africa": "South Africa",
    "kenya": "Kenya",
    "ghana": "Ghana",
    "egypt": "Egypt",
    "israel": "Israel",
    "turkey": "Turkey",
    "türkiye": "Turkey",
    "russia": "Russia",
    "ukraine": "Ukraine",
    "poland": "Poland",
    "romania": "Romania",
    "greece": "Greece",
    "hungary": "Hungary",
    "ireland": "Ireland",
    "croatia": "Croatia",
    "serbia": "Serbia",
    "slovakia": "Slovakia",
    "bulgaria": "Bulgaria",
    "slovenia": "Slovenia",
    "luxembourg": "Luxembourg",
    "malta": "Malta",
    "cyprus": "Cyprus",
    "estonia": "Estonia",
    "latvia": "Latvia",
    "lithuania": "Lithuania",
    "saudi arabia": "Saudi Arabia",
    "ksa": "Saudi Arabia",
    "qatar": "Qatar",
    "kuwait": "Kuwait",
    "bahrain": "Bahrain",
    "oman": "Oman",
    "jordan": "Jordan",
    "lebanon": "Lebanon",
    "iraq": "Iraq",
    "iran": "Iran",
    "morocco": "Morocco",
    "algeria": "Algeria",
    "tunisia": "Tunisia",
    "ethiopia": "Ethiopia",
    "tanzania": "Tanzania",
    "uganda": "Uganda",
    "zimbabwe": "Zimbabwe",
    "new caledonia": "New Caledonia",
    "puerto rico": "Puerto Rico",
    "remote": "Remote",
    "worldwide": "Worldwide",
    "global": "Global",
}


def clean_location(val) -> str:
    """
    Standardize location to country level.
    'Boston, Massachusetts' → 'United States'
    'London, UK' → 'United Kingdom'
    """
    if pd.isna(val) or str(val).strip() == "":
        return ""

    raw = str(val).strip()
    text = _strip_emojis(raw)
    text = re.sub(r"\s{2,}", " ", text).strip()

    # Split on comma — last part is often the country/state
    parts = [p.strip() for p in text.split(",")]

    # Check each part from right to left
    for part in reversed(parts):
        key = part.strip().lower().strip(".")
        # Direct country alias match
        if key in COUNTRY_ALIASES:
            return COUNTRY_ALIASES[key]
        # US state name
        if key in US_STATES:
            return "United States"
        # US state abbreviation (only if short)
        if len(key) == 2 and key in US_STATE_ABBREVS:
            return "United States"

    # Try whole string as a country alias
    key = text.lower().strip(".")
    if key in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[key]
    if key in US_STATES:
        return "United States"

    # Try pycountry as fallback
    try:
        import pycountry
        for part in reversed(parts):
            result = pycountry.countries.get(name=part.strip())
            if result:
                return result.name
            # fuzzy search
            results = pycountry.countries.search_fuzzy(part.strip())
            if results:
                return results[0].name
    except Exception:
        pass

    # Return cleaned original if we can't resolve
    return text


# ── Column detection ──────────────────────────────────────────────────────────

# Maps common raw column name variations to our canonical names
COLUMN_MAP = {
    # first name
    "first name": "first_name",
    "firstname": "first_name",
    "first_name": "first_name",
    "given name": "first_name",
    # last name
    "last name": "last_name",
    "lastname": "last_name",
    "last_name": "last_name",
    "surname": "last_name",
    "family name": "last_name",
    # job title
    "job title": "job_title",
    "jobtitle": "job_title",
    "job_title": "job_title",
    "title": "job_title",
    "position": "job_title",
    "role": "job_title",
    # linkedin
    "linkedin": "linkedin_url",
    "linkedin url": "linkedin_url",
    "linkedin_url": "linkedin_url",
    "linkedin profile": "linkedin_url",
    "profile url": "linkedin_url",
    # company
    "company": "company",
    "company name": "company",
    "organization": "company",
    "organisation": "company",
    "employer": "company",
    # location / country
    "location": "location",
    "country": "location",
    "country/region": "location",
    "region": "location",
    "city": "location",
    "city, state": "location",
    "city/state": "location",
}


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename columns to canonical names based on COLUMN_MAP."""
    rename = {}
    for col in df.columns:
        key = col.strip().lower()
        if key in COLUMN_MAP:
            rename[col] = COLUMN_MAP[key]
    return df.rename(columns=rename)


# ── Master clean function ─────────────────────────────────────────────────────

FIELD_CLEANERS = {
    "first_name": clean_first_name,
    "last_name": clean_last_name,
    "job_title": clean_job_title,
    "linkedin_url": clean_linkedin_url,
    "company": clean_company_name,
    "location": clean_location,
}


def clean_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """
    Apply all hard cleaning rules to recognized columns.
    Returns (cleaned_df, change_counts) where change_counts maps column → number of cells changed.
    """
    df = normalize_columns(df.copy())
    change_counts: dict[str, int] = {}

    for col, fn in FIELD_CLEANERS.items():
        if col not in df.columns:
            continue
        original = df[col].copy()
        df[col] = df[col].apply(fn)
        changed = (df[col] != original.apply(lambda v: fn(v) if not pd.isna(v) else "")).sum()
        # Simpler: count rows where value actually changed
        original_str = original.fillna("").astype(str)
        new_str = df[col].fillna("").astype(str)
        change_counts[col] = int((original_str != new_str).sum())

    return df, change_counts
