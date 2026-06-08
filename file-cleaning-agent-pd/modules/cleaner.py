"""
Hard cleaning rules for File Cleaning Agent PD.

Pipeline (applied in order):
  1. Strip hidden chars (\n \r \t), collapse whitespace
  2. Remove emojis & symbol characters
  3. Remove honorific prefixes (Dr., Ing., MUDr., etc.)
  4. Remove parentheticals  e.g. Archana (Arch) → Archana
  5. Remove middle initials  e.g. Amy H. → Amy
  6. Remove trailing punctuation dots
  7. Fix casing (all-caps / all-lower / hyphenated segments)
  8. Multi-word first-name resolution via LinkedIn slug
  9. First/Last swap detection via LinkedIn slug
 10. Junk-row detection (company accounts, non-Latin, single-letter)
 11. Single-quote removal across every column
 12. Honorific sweep across every text column (not just name fields)
 13. Phone number normalisation → +[digits], no dashes/brackets/spaces
"""

import re
import unicodedata
import pandas as pd


# ── Emoji & symbol removal ────────────────────────────────────────────────────

_EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0001FFFF"   # Emoticons, pictographs, transport, misc symbols
    "\U00002600-\U000027BF"   # Misc symbols (★☆♠♣…)
    "\U0000FE00-\U0000FE0F"   # Variation selectors
    "\U00020000-\U0010FFFF"   # Supplementary CJK, tags, etc.
    "]+",
    flags=re.UNICODE,
)


def _strip_emojis(text: str) -> str:
    return _EMOJI_RE.sub("", text)


# ── Hidden / control character removal ───────────────────────────────────────

def _strip_hidden(text: str) -> str:
    """Replace \n \r \t and other control chars with a space, then collapse."""
    text = re.sub(r"[\r\n\t\x0B\x0C\x00-\x1F\x7F]", " ", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


# ── Honorific prefixes ────────────────────────────────────────────────────────

_HONORIFIC_RE = re.compile(
    r"^("
    r"Dr\.?\s+rer\.?\s+nat\.?"   # Dr. rer. nat.
    r"|MUDr\.?"                   # Czech/Slovak medical degree prefix
    r"|PhDr\.?"                   # Czech humanties doctoral prefix
    r"|Ing\.?"                    # Engineer prefix (European)
    r"|Prof\.?"                   # Professor
    r"|Dr\.?"                     # Doctor
    r"|Mr\.?"                     # Mister
    r"|Mrs\.?"                    # Missus
    r"|Ms\.?"                     # Miss / Ms
    r"|Rev\.?"                    # Reverend
    r"|Sir"
    r"|Lord"
    r"|Lady"
    r"|Hon\.?"                    # Honorable
    r"|Capt\.?"                   # Captain
    r"|Col\.?"                    # Colonel
    r"|Gen\.?"                    # General
    r"|Lt\.?"                     # Lieutenant
    r"|Sgt\.?"                    # Sergeant
    r")\s+",
    re.IGNORECASE,
)


def _strip_honorifics(text: str) -> str:
    """Remove leading title prefixes, repeatedly (handles 'Dr. Prof. Name')."""
    prev = None
    while prev != text:
        prev = text
        text = _HONORIFIC_RE.sub("", text, count=1).strip()
    return text


# ── Credential / suffix removal ───────────────────────────────────────────────

_CREDENTIAL_SUFFIX_RE = re.compile(
    r"[,\s]+"
    r"("
    r"M\.?D\.?"
    r"|Ph\.?D\.?"
    r"|M\.?B\.?A\.?"
    r"|M\.?Sc\.?"
    r"|B\.?Sc\.?"
    r"|B\.?A\.?"
    r"|D\.?O\.?"
    r"|D\.?D\.?S\.?"
    r"|D\.?V\.?M\.?"
    r"|J\.?D\.?"
    r"|R\.?N\.?"
    r"|N\.?P\.?"
    r"|C\.?P\.?A\.?"
    r"|C\.?F\.?A\.?"
    r"|P\.?M\.?P\.?"
    r"|Esq\.?"
    r"|Jr\.?"
    r"|Sr\.?"
    r"|I{2,3}V?"        # II, III, IV
    r"|OG"
    r")"
    r"(?:[,\s].*)?$",   # drop everything after the credential too
    re.IGNORECASE,
)


def _strip_credential_suffixes(text: str) -> str:
    return _CREDENTIAL_SUFFIX_RE.sub("", text).strip()


# ── Parenthetical removal  e.g. "Jean Francois (JF)" → "Jean Francois" ───────

_PAREN_RE = re.compile(r"\s*\(.*?\)\s*")


def _strip_parentheticals(text: str) -> str:
    return _PAREN_RE.sub(" ", text).strip()


# ── Middle initial removal  e.g. "Amy H." → "Amy" (for first-name field) ─────

_MIDDLE_INITIAL_RE = re.compile(r"\s+[A-Z]\.$")


def _strip_middle_initial(text: str) -> str:
    return _MIDDLE_INITIAL_RE.sub("", text).strip()


# ── Trailing / leading punctuation ────────────────────────────────────────────

def _strip_edge_punct(text: str) -> str:
    return text.strip(".,;:!?\"'`-")


# ── Casing ────────────────────────────────────────────────────────────────────

def _smart_case(text: str) -> str:
    """
    Title-case a name, respecting:
    - Hyphenated segments: Jean-Marc → Jean-Marc
    - All-caps tokens: VIRGINIA → Virginia
    - All-lower tokens: virginia → Virginia
    - Short particles left lower (de, van, von, da, dos) when mid-name
    """
    PARTICLES = {"de", "van", "von", "da", "dos", "del", "della", "le", "la", "les", "el", "al"}

    def cap_segment(s: str) -> str:
        # Handle hyphenated compound segments
        parts = s.split("-")
        return "-".join(p.capitalize() for p in parts if p)

    tokens = text.split()
    result = []
    for i, tok in enumerate(tokens):
        lower = tok.lower()
        if i > 0 and lower in PARTICLES:
            result.append(lower)
        else:
            result.append(cap_segment(tok))
    return " ".join(result)


# ── LinkedIn slug helpers ─────────────────────────────────────────────────────

def _slug_from_linkedin(url) -> str | None:
    """Extract the profile slug from a LinkedIn URL, e.g. 'jean-francois-martin'."""
    if pd.isna(url) or not str(url).strip():
        return None
    m = re.search(r"linkedin\.com/in/([^/?#]+)", str(url), re.IGNORECASE)
    if not m:
        return None
    return m.group(1).lower().strip("/")


def _slug_tokens(slug: str) -> list[str]:
    """Split slug on hyphens, strip numeric suffixes like '-ab1234'."""
    parts = slug.split("-")
    # Drop trailing parts that look like random IDs (short alphanum)
    cleaned = [p for p in parts if p and not re.fullmatch(r"[a-z]{1,2}\d+", p)]
    return cleaned


# ── Junk-row detection ────────────────────────────────────────────────────────

# Unicode script ranges for non-Latin scripts
_NON_LATIN_RE = re.compile(
    r"[Ѐ-ӿ"   # Cyrillic
    r"一-鿿"    # CJK Unified
    r"぀-ヿ"    # Hiragana / Katakana
    r"가-힯"    # Korean Hangul
    r"؀-ۿ"    # Arabic
    r"ऀ-ॿ"    # Devanagari
    r"]",
)


def is_junk_name(first: str, last: str) -> bool:
    """Return True if this row looks like a company account or garbage."""
    full = f"{first} {last}".strip()
    if not full:
        return False
    # Single-character name
    if len(full.replace(" ", "")) <= 1:
        return True
    # Non-Latin script
    if _NON_LATIN_RE.search(full):
        return True
    # Looks like a company (contains Inc, LLC, Ltd, Corp, &, @, digits)
    if re.search(r"\b(Inc\.?|LLC|Ltd\.?|Corp\.?|GmbH|S\.A\.?)\b", full, re.IGNORECASE):
        return True
    if re.search(r"[@&]|\d{3,}", full):
        return True
    return False


# ── Core name cleaner ─────────────────────────────────────────────────────────

def _base_name_clean(val) -> str:
    """Apply the shared pipeline steps to any name value."""
    if pd.isna(val) or str(val).strip() == "":
        return ""
    text = str(val)
    text = _strip_hidden(text)
    text = _strip_emojis(text)
    text = _strip_parentheticals(text)
    text = _strip_honorifics(text)
    text = _strip_credential_suffixes(text)
    text = _strip_edge_punct(text)
    # Remove junk special chars (but keep hyphens and apostrophes for names)
    text = re.sub(r'[!@#$%^&*()+=\[\]{};\\|<>?/~`\"]', "", text)
    text = re.sub(r" {2,}", " ", text).strip()
    return text


# ── First name ────────────────────────────────────────────────────────────────

def clean_first_name(val, linkedin_url=None) -> str:
    text = _base_name_clean(val)
    if not text:
        return ""

    # Remove middle initial (only relevant for first-name field)
    text = _strip_middle_initial(text)

    tokens = text.split()

    # Multi-word first name: use LinkedIn slug to decide how many words belong
    if len(tokens) >= 2 and linkedin_url:
        slug = _slug_from_linkedin(linkedin_url)
        if slug:
            slug_toks = _slug_tokens(slug)
            # Count how many leading tokens of 'text' match slug tokens
            match_count = 0
            for tok in tokens:
                if match_count < len(slug_toks) and tok.lower() == slug_toks[match_count]:
                    match_count += 1
                else:
                    break
            # If slug starts with first token only, keep just first token
            if match_count == 1:
                tokens = tokens[:1]
            # If slug confirms 2+ tokens as first name (e.g. 'maria-del-mar'), keep them
            elif match_count >= 2 and match_count <= 3:
                tokens = tokens[:match_count]
            else:
                tokens = tokens[:1]
        else:
            # No LinkedIn — conservatively keep only the first token
            tokens = tokens[:1]

    result = " ".join(tokens)
    return _smart_case(result)


# ── Last name ─────────────────────────────────────────────────────────────────

def clean_last_name(val) -> str:
    text = _base_name_clean(val)
    if not text:
        return ""
    return _smart_case(text)


# ── Job title ─────────────────────────────────────────────────────────────────

def clean_job_title(val) -> str:
    if pd.isna(val) or str(val).strip() == "":
        return ""
    text = str(val)
    text = _strip_hidden(text)
    text = _strip_emojis(text)
    # Remove non-printable control chars
    text = "".join(ch for ch in text if unicodedata.category(ch)[0] != "C")
    text = re.sub(r" {2,}", " ", text).strip()
    return text


# ── LinkedIn URL ──────────────────────────────────────────────────────────────

def clean_linkedin_url(val) -> str:
    if pd.isna(val) or str(val).strip() == "":
        return ""
    url = str(val).strip()
    if not url.startswith("http"):
        url = "https://" + url
    url = re.sub(r"\?.*$", "", url)   # strip tracking params
    return url.rstrip("/")


# ── Company name ──────────────────────────────────────────────────────────────

def clean_company_name(val) -> str:
    if pd.isna(val) or str(val).strip() == "":
        return ""
    text = str(val)
    text = _strip_hidden(text)
    text = _strip_emojis(text)
    text = re.sub(r'[!@#$%^&*()+=\[\]{};\'\\|<>?/~`\"]', "", text)
    text = re.sub(r"-{2,}", "-", text)        # double hyphens → single
    text = re.sub(r"(^-+|-+$)", "", text)     # leading/trailing hyphens
    text = "".join(ch for ch in text if unicodedata.category(ch)[0] != "C")
    text = re.sub(r" {2,}", " ", text).strip()
    return text


# ── Location → Country ────────────────────────────────────────────────────────

US_STATES = {
    "alabama","alaska","arizona","arkansas","california","colorado",
    "connecticut","delaware","florida","georgia","hawaii","idaho",
    "illinois","indiana","iowa","kansas","kentucky","louisiana",
    "maine","maryland","massachusetts","michigan","minnesota",
    "mississippi","missouri","montana","nebraska","nevada",
    "new hampshire","new jersey","new mexico","new york",
    "north carolina","north dakota","ohio","oklahoma","oregon",
    "pennsylvania","rhode island","south carolina","south dakota",
    "tennessee","texas","utah","vermont","virginia","washington",
    "west virginia","wisconsin","wyoming","district of columbia",
    "dc","d.c.",
}

US_STATE_ABBREVS = {
    "al","ak","az","ar","ca","co","ct","de","fl","ga","hi","id","il","in",
    "ia","ks","ky","la","me","md","ma","mi","mn","ms","mo","mt","ne","nv",
    "nh","nj","nm","ny","nc","nd","oh","ok","or","pa","ri","sc","sd","tn",
    "tx","ut","vt","va","wa","wv","wi","wy","dc",
}

COUNTRY_ALIASES: dict[str, str] = {
    "united states":"United States","united states of america":"United States",
    "usa":"United States","u.s.a.":"United States","u.s.":"United States","us":"United States",
    "uk":"United Kingdom","united kingdom":"United Kingdom","great britain":"United Kingdom",
    "england":"United Kingdom","scotland":"United Kingdom","wales":"United Kingdom",
    "northern ireland":"United Kingdom",
    "uae":"United Arab Emirates","u.a.e.":"United Arab Emirates","united arab emirates":"United Arab Emirates",
    "south korea":"South Korea","republic of korea":"South Korea","korea":"South Korea",
    "north korea":"North Korea","dprk":"North Korea",
    "czech republic":"Czech Republic","czechia":"Czech Republic",
    "taiwan":"Taiwan","hong kong":"Hong Kong","singapore":"Singapore",
    "canada":"Canada","australia":"Australia","new zealand":"New Zealand",
    "germany":"Germany","deutschland":"Germany",
    "france":"France","spain":"Spain","españa":"Spain",
    "italy":"Italy","italia":"Italy",
    "netherlands":"Netherlands","the netherlands":"Netherlands","holland":"Netherlands",
    "switzerland":"Switzerland","sweden":"Sweden","norway":"Norway",
    "denmark":"Denmark","finland":"Finland","belgium":"Belgium",
    "austria":"Austria","portugal":"Portugal","poland":"Poland",
    "brazil":"Brazil","brasil":"Brazil",
    "mexico":"Mexico","méxico":"Mexico",
    "argentina":"Argentina","chile":"Chile","colombia":"Colombia","peru":"Peru",
    "india":"India","china":"China","japan":"Japan","indonesia":"Indonesia",
    "malaysia":"Malaysia","philippines":"Philippines","thailand":"Thailand",
    "vietnam":"Vietnam","pakistan":"Pakistan","bangladesh":"Bangladesh",
    "nigeria":"Nigeria","south africa":"South Africa","kenya":"Kenya",
    "ghana":"Ghana","egypt":"Egypt","israel":"Israel",
    "turkey":"Turkey","türkiye":"Turkey",
    "russia":"Russia","ukraine":"Ukraine","romania":"Romania",
    "greece":"Greece","hungary":"Hungary","ireland":"Ireland",
    "croatia":"Croatia","serbia":"Serbia","slovakia":"Slovakia",
    "bulgaria":"Bulgaria","slovenia":"Slovenia","luxembourg":"Luxembourg",
    "malta":"Malta","cyprus":"Cyprus","estonia":"Estonia",
    "latvia":"Latvia","lithuania":"Lithuania",
    "saudi arabia":"Saudi Arabia","ksa":"Saudi Arabia",
    "qatar":"Qatar","kuwait":"Kuwait","bahrain":"Bahrain","oman":"Oman",
    "jordan":"Jordan","lebanon":"Lebanon","iraq":"Iraq","iran":"Iran",
    "morocco":"Morocco","algeria":"Algeria","tunisia":"Tunisia",
    "ethiopia":"Ethiopia","tanzania":"Tanzania","uganda":"Uganda","zimbabwe":"Zimbabwe",
    "remote":"Remote","worldwide":"Worldwide","global":"Global",
}


def clean_location(val) -> str:
    if pd.isna(val) or str(val).strip() == "":
        return ""
    text = _strip_hidden(str(val))
    text = _strip_emojis(text)

    parts = [p.strip() for p in text.split(",")]

    # Check parts right-to-left (country/state usually last)
    for part in reversed(parts):
        key = part.lower().strip(".")
        if key in COUNTRY_ALIASES:
            return COUNTRY_ALIASES[key]
        if key in US_STATES:
            return "United States"
        if len(key) == 2 and key in US_STATE_ABBREVS:
            return "United States"

    # Try whole string
    key = text.lower().strip(".")
    if key in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[key]
    if key in US_STATES:
        return "United States"

    # pycountry fuzzy fallback
    try:
        import pycountry
        for part in reversed(parts):
            p = part.strip()
            result = pycountry.countries.get(name=p)
            if result:
                return result.name
            try:
                results = pycountry.countries.search_fuzzy(p)
                if results:
                    return results[0].name
            except LookupError:
                pass
    except Exception:
        pass

    return text  # return cleaned original if unresolvable


# ── Phone number normalisation ───────────────────────────────────────────────
#
# Rules:
#   - Digits are NEVER altered — only formatting chars are removed
#   - Output format: +[country-code][number]  e.g. +14155550123
#   - Handles: +1 (415) 555-0123 / 0044 20 7946 0958 / (415) 555-0123
#   - Leading 00 → + (international dialling prefix)
#   - If no + or 00 prefix the digits are returned as-is (no country code injected)

_PHONE_COLUMNS = {
    "phone", "phone_number", "mobile", "mobile_number", "telephone",
    "tel", "cell", "cell_phone", "work_phone", "direct_phone",
    "phone 1", "phone 2", "phone1", "phone2",
    "enriched phone number 1", "enriched phone number 2",
    "enriched_phone_number_1", "enriched_phone_number_2",
}


def clean_phone(val) -> str:
    if pd.isna(val) or str(val).strip() == "":
        return ""
    raw = str(val).strip()

    # Remove single quotes, hidden chars, emojis first
    raw = raw.replace("'", "")
    raw = _strip_hidden(raw)
    raw = _strip_emojis(raw)

    # Detect leading + before we strip everything
    has_plus = raw.lstrip().startswith("+")

    # Replace leading international prefix 00 with +
    no_prefix = re.sub(r"^\s*00", "+", raw)
    if no_prefix != raw:
        has_plus = True
        raw = no_prefix

    # Strip every non-digit character (keeps digits only)
    digits = re.sub(r"\D", "", raw)

    if not digits:
        return ""

    # Always ensure a + prefix regardless of whether one was present originally
    return f"+{digits}"


# ── Global column sweeps ──────────────────────────────────────────────────────

# Columns that must NEVER have honorifics removed (they're not name/title fields)
_NO_HONORIFIC_COLS = {
    "linkedin_url", "company_domain", "email", "business_email",
    "phone", "phone_number", "mobile", "website", "url",
}

# Columns that are purely numeric / identifiers — skip quote removal too
_NUMERIC_ID_COLS = {
    "phone", "phone_number", "mobile", "mobile_number", "telephone", "tel",
    "cell", "cell_phone", "work_phone", "direct_phone",
    "phone 1", "phone 2", "phone1", "phone2",
    "enriched phone number 1", "enriched phone number 2",
    "enriched_phone_number_1", "enriched_phone_number_2",
    "zip", "zip_code", "postal_code", "id", "record_id",
}


def _sweep_honorifics(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """
    Remove honorific prefixes from every text column that isn't a URL,
    email, or numeric/phone field.
    Returns (df, total_cells_changed).
    """
    changed = 0
    for col in df.columns:
        if col.lower() in _NO_HONORIFIC_COLS:
            continue
        if not (df[col].dtype == object or pd.api.types.is_string_dtype(df[col])):
            continue
        orig = df[col].copy()
        df[col] = df[col].apply(
            lambda v: _strip_honorifics(str(v)).strip() if pd.notna(v) and str(v).strip() else (v if pd.isna(v) else str(v))
        )
        changed += int((df[col].fillna("") != orig.fillna("")).sum())
    return df, changed


def _sweep_quotes(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    # Remove straight and smart/curly quotes from every column.
    # All quote chars as Unicode escapes - zero curly bytes in this source file.
    _cps = [0x27,0x22,0x2018,0x2019,0x201a,0x201b,0x201c,0x201d,0x201e,0x201f,0x2032,0x2033]
    _QUOTE_PAT = re.compile('[' + ''.join(chr(c) for c in _cps) + ']')
    changed = 0
    for col in df.columns:
        if not (df[col].dtype == object or pd.api.types.is_string_dtype(df[col])):
            continue
        orig = df[col].astype(str).copy()
        df[col] = df[col].apply(
            lambda v: _QUOTE_PAT.sub('', str(v)) if pd.notna(v) else v
        )
        changed += int((df[col].astype(str).fillna('') != orig.fillna('')).sum())
    return df, changed


# ── Column name normalisation ─────────────────────────────────────────────────

COLUMN_MAP = {
    "first name":"first_name","firstname":"first_name","first_name":"first_name","given name":"first_name",
    "last name":"last_name","lastname":"last_name","last_name":"last_name","surname":"last_name","family name":"last_name",
    "job title":"job_title","jobtitle":"job_title","job_title":"job_title","title":"job_title","position":"job_title","role":"job_title",
    "linkedin":"linkedin_url","linkedin url":"linkedin_url","linkedin_url":"linkedin_url",
    "linkedin profile":"linkedin_url","profile url":"linkedin_url",
    "company":"company","company name":"company","organization":"company","organisation":"company","employer":"company",
    "location":"location","country":"location","country/region":"location","region":"location",
    "city":"location","city, state":"location","city/state":"location","city, country":"location",
    # phone variants → canonical "phone"
    "phone":"phone","phone number":"phone","phone_number":"phone",
    "mobile":"phone","mobile number":"phone","mobile_number":"phone",
    "telephone":"phone","tel":"phone","cell":"phone","cell phone":"phone",
    "work phone":"phone","direct phone":"phone",
    "phone 1":"phone_1","phone 2":"phone_2",
    "enriched phone number 1":"phone_1","enriched phone number 2":"phone_2",
    "enriched_phone_number_1":"phone_1","enriched_phone_number_2":"phone_2",
}

# Columns that get the phone cleaner applied
_PHONE_CANONICAL = {"phone", "phone_1", "phone_2"}

FIELD_CLEANERS = {
    "first_name":   None,   # handled specially (needs linkedin_url)
    "last_name":    clean_last_name,
    "job_title":    clean_job_title,
    "linkedin_url": clean_linkedin_url,
    "company":      clean_company_name,
    "location":     clean_location,
    "phone":        clean_phone,
    "phone_1":      clean_phone,
    "phone_2":      clean_phone,
}


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename = {}
    for col in df.columns:
        key = col.strip().lower()
        if key in COLUMN_MAP:
            rename[col] = COLUMN_MAP[key]
    return df.rename(columns=rename)


# ── Master clean function ─────────────────────────────────────────────────────

def clean_dataframe(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """
    Apply all hard cleaning rules to recognized columns.
    Returns (cleaned_df, change_counts).
    """
    df = normalize_columns(df.copy())
    change_counts: dict[str, int] = {}

    # ── Pass 0: global sweeps (all text columns) ──────────────────────────────

    # Remove single and double quotes (including smart/curly variants) from every non-numeric column
    df, sq_changes = _sweep_quotes(df)
    if sq_changes:
        change_counts["_global_quotes"] = sq_changes

    # Remove honorifics from every text column that isn't a URL/email/phone
    df, hon_changes = _sweep_honorifics(df)
    if hon_changes:
        change_counts["_global_honorifics"] = hon_changes

    # ── Pass 1: LinkedIn URL (needed for first_name resolution) ───────────────
    if "linkedin_url" in df.columns:
        orig = df["linkedin_url"].fillna("").astype(str)
        df["linkedin_url"] = df["linkedin_url"].apply(clean_linkedin_url)
        change_counts["linkedin_url"] = int((df["linkedin_url"].fillna("").astype(str) != orig).sum())

    # ── Pass 2: first_name (needs linkedin_url for slug resolution) ───────────
    if "first_name" in df.columns:
        orig = df["first_name"].fillna("").astype(str)
        linkedin_series = df.get("linkedin_url", pd.Series([""] * len(df)))
        df["first_name"] = [
            clean_first_name(fn, li)
            for fn, li in zip(df["first_name"], linkedin_series)
        ]
        change_counts["first_name"] = int((df["first_name"].fillna("").astype(str) != orig).sum())

    # ── Pass 3: remaining named-column cleaners ───────────────────────────────
    for col, fn in FIELD_CLEANERS.items():
        if fn is None or col not in df.columns:
            continue
        orig = df[col].fillna("").astype(str)
        df[col] = df[col].apply(fn)
        change_counts[col] = int((df[col].fillna("").astype(str) != orig).sum())

    # ── Pass 4: phone cleaner on any remaining phone-like columns ─────────────
    for col in df.columns:
        col_lower = col.lower().replace(" ", "_")
        if col_lower in _PHONE_COLUMNS and col not in _PHONE_CANONICAL:
            orig = df[col].fillna("").astype(str)
            df[col] = df[col].apply(clean_phone)
            n = int((df[col].fillna("").astype(str) != orig).sum())
            if n:
                change_counts[col] = n

    # ── Flag junk rows (review panel — not auto-deleted) ─────────────────────
    if "first_name" in df.columns and "last_name" in df.columns:
        df["_junk_flag"] = df.apply(
            lambda r: is_junk_name(str(r["first_name"]), str(r["last_name"])),
            axis=1,
        )

    return df, change_counts
