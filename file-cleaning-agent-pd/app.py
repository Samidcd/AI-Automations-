"""File Cleaning Agent PD — Streamlit UI."""

import io
import pandas as pd
import streamlit as st

from modules import cleaner, loader

st.set_page_config(
    page_title="File Cleaning Agent PD",
    page_icon="🧹",
    layout="wide",
)

st.markdown(
    """
    <style>
    .rule-badge {
        display: inline-block;
        background: #1e2a3a;
        border: 1px solid #4f8ef7;
        border-radius: 6px;
        padding: 4px 10px;
        font-size: 0.82rem;
        color: #a0c4ff;
        margin: 3px 4px;
    }
    .change-pill {
        background: #1a3a1a;
        border: 1px solid #3cba3c;
        border-radius: 4px;
        padding: 2px 8px;
        font-size: 0.8rem;
        color: #7eff7e;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Session state ──────────────────────────────────────────────────────────────
for k, v in {
    "raw_df": None,
    "cleaned_df": None,
    "change_counts": {},
    "source": "file",
    "sheet_url": "",
    "worksheet_index": 0,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ── Header ─────────────────────────────────────────────────────────────────────
st.title("🧹 File Cleaning Agent PD")
st.caption("Hard-rule data cleaning — names, titles, companies, LinkedIn URLs, and locations.")

st.markdown(
    """
    <div style="margin-bottom:1rem">
    <span class="rule-badge">First Name — first name only, no titles or credentials</span>
    <span class="rule-badge">Last Name — no OG / ! / extras</span>
    <span class="rule-badge">Job Title — no emojis or junk chars</span>
    <span class="rule-badge">LinkedIn URL — normalized & intact</span>
    <span class="rule-badge">Company — no extra hyphens or emojis</span>
    <span class="rule-badge">Location → Country (e.g. Boston, MA → United States)</span>
    <span class="rule-badge">Phone → +[digits] only, no dashes/brackets/spaces</span>
    <span class="rule-badge">All columns — single &amp; double quotes removed (' " ' ' " ")</span>
    <span class="rule-badge">All text columns — honorifics swept out</span>
    </div>
    """,
    unsafe_allow_html=True,
)
st.divider()


# ── Sidebar — Google Sheets credentials ────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Settings")
    st.divider()
    sa_json = st.text_area(
        "Google Service Account JSON",
        height=160,
        help="Required only for Google Sheets import. Paste the full JSON.",
    )


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — Import
# ══════════════════════════════════════════════════════════════════════════════
st.subheader("1 · Import")

file_tab, gsheet_tab = st.tabs(["📂 Upload File (CSV / Excel)", "📊 Google Sheet URL"])

with file_tab:
    uploaded = st.file_uploader("Drop your file here", type=["csv", "xlsx", "xls"])
    if uploaded and st.button("Load File →", type="primary", key="load_file"):
        with st.spinner("Reading file…"):
            try:
                df = loader.load_file(uploaded)
                st.session_state.raw_df = df
                st.session_state.cleaned_df = None
                st.session_state.source = "file"
                st.success(f"Loaded **{len(df)} rows** · {len(df.columns)} columns")
            except Exception as e:
                st.error(f"Could not read file: {e}")

with gsheet_tab:
    sheet_url = st.text_input(
        "Google Sheet URL",
        value=st.session_state.sheet_url,
        placeholder="https://docs.google.com/spreadsheets/d/…",
    )
    worksheet_index = st.number_input("Tab index (0 = first tab)", min_value=0, value=0, step=1)

    if not sa_json:
        st.info("Paste your Service Account JSON in the sidebar to enable Google Sheets import.")

    if st.button(
        "Pull Sheet →",
        type="primary",
        key="load_gsheet",
        disabled=not (sheet_url and sa_json),
    ):
        with st.spinner("Connecting to Google Sheets…"):
            try:
                df = loader.load_gsheet(sheet_url, sa_json, int(worksheet_index))
                st.session_state.raw_df = df
                st.session_state.cleaned_df = None
                st.session_state.sheet_url = sheet_url
                st.session_state.worksheet_index = int(worksheet_index)
                st.session_state.source = "gsheet"
                st.success(f"Loaded **{len(df)} rows** · {len(df.columns)} columns")
            except Exception as e:
                st.error(f"Could not read sheet: {e}")

if st.session_state.raw_df is not None:
    raw = st.session_state.raw_df
    with st.expander("Preview raw data", expanded=False):
        st.dataframe(raw.head(10), use_container_width=True)

st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — Clean
# ══════════════════════════════════════════════════════════════════════════════
st.subheader("2 · Clean")

if st.session_state.raw_df is None:
    st.info("Import a file or Google Sheet above to get started.")
else:
    raw = st.session_state.raw_df

    # Show which columns will be cleaned
    normalized_cols = cleaner.normalize_columns(raw).columns.tolist()
    recognized = [c for c in cleaner.FIELD_CLEANERS if c in normalized_cols]
    unrecognized = [c for c in normalized_cols if c not in cleaner.FIELD_CLEANERS]

    col_a, col_b = st.columns(2)
    col_a.markdown(f"**Columns that will be cleaned ({len(recognized)}):**")
    if recognized:
        col_a.markdown(" · ".join(f"`{c}`" for c in recognized))
    else:
        col_a.warning("No recognized columns found — check column names match expected names.")

    col_b.markdown(f"**Pass-through columns ({len(unrecognized)}):**")
    col_b.markdown(" · ".join(f"`{c}`" for c in unrecognized) or "_none_")

    if st.button("🧹 Run Cleaning Agent", type="primary", disabled=not recognized):
        with st.spinner("Applying hard cleaning rules…"):
            cleaned, changes = cleaner.clean_dataframe(raw)
            st.session_state.cleaned_df = cleaned
            st.session_state.change_counts = changes

        total_changes = sum(changes.values())
        st.success(f"Done — **{total_changes} cells updated** across {len(changes)} columns.")

        # Change summary
        if changes:
            LABEL_MAP = {
                "_global_quotes":        "Quote removal ' \" (all cols)",
                "_global_honorifics":    "Honorific sweep (all cols)",
            }
            st.markdown("**Changes by column:**")
            cols_ui = st.columns(min(len(changes), 4))
            for i, (col, count) in enumerate(changes.items()):
                label = LABEL_MAP.get(col, col)
                cols_ui[i % len(cols_ui)].markdown(
                    f"<span class='change-pill'>`{label}` — {count} cells</span>",
                    unsafe_allow_html=True,
                )

st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — Review & Export
# ══════════════════════════════════════════════════════════════════════════════
st.subheader("3 · Review & Export")

if st.session_state.cleaned_df is None:
    st.info("Run the cleaning agent above to see results.")
else:
    cleaned = st.session_state.cleaned_df
    raw = st.session_state.raw_df

    # Side-by-side diff viewer
    diff_col = st.selectbox(
        "Compare column (before vs after):",
        options=[c for c in cleaner.FIELD_CLEANERS if c in cleaned.columns],
    )

    if diff_col:
        raw_normalized = cleaner.normalize_columns(raw.copy())
        before = raw_normalized[diff_col].fillna("").astype(str) if diff_col in raw_normalized.columns else pd.Series([""] * len(cleaned))
        after = cleaned[diff_col].fillna("").astype(str)
        changed_mask = before != after
        n_changed = int(changed_mask.sum())

        if n_changed == 0:
            st.success(f"No changes in `{diff_col}`.")
        else:
            st.markdown(f"**{n_changed} rows changed in `{diff_col}`:**")
            diff_df = pd.DataFrame({
                "Before": before[changed_mask].values,
                "After": after[changed_mask].values,
            })
            st.dataframe(diff_df, use_container_width=True)

    # ── Junk row review ────────────────────────────────────────────────────────
    if "_junk_flag" in cleaned.columns:
        junk = cleaned[cleaned["_junk_flag"] == True].drop(columns=["_junk_flag"])
        good = cleaned[cleaned["_junk_flag"] != True].drop(columns=["_junk_flag"])
        if len(junk) > 0:
            with st.expander(f"⚠️ {len(junk)} suspected junk / company rows — review before export", expanded=True):
                st.caption(
                    "These rows were flagged because the name looks like a company account, "
                    "contains non-Latin characters, or is a single letter. "
                    "They are excluded from the export below — download separately if needed."
                )
                st.dataframe(junk, use_container_width=True)
                junk_csv = junk.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    "⬇️ Download flagged rows",
                    data=junk_csv,
                    file_name="flagged_rows.csv",
                    mime="text/csv",
                )
            cleaned = good  # exclude junk from main export
        else:
            st.success("No junk rows detected.")
    else:
        good = cleaned

    st.divider()
    st.markdown("**Full cleaned dataset:**")
    display_df = cleaned.drop(columns=["_junk_flag"], errors="ignore")
    st.dataframe(display_df.head(50), use_container_width=True)

    st.divider()
    st.markdown("**Download:**")
    dl1, dl2 = st.columns(2)

    export_df = cleaned.drop(columns=["_junk_flag"], errors="ignore")

    # utf-8-sig = UTF-8 with BOM — Excel renders accented chars (é ü ñ) correctly
    csv_bytes = export_df.to_csv(index=False).encode("utf-8-sig")
    dl1.download_button(
        "⬇️ Download CSV",
        data=csv_bytes,
        file_name="cleaned_leads.csv",
        mime="text/csv",
        type="primary",
    )

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name="Cleaned")
    dl2.download_button(
        "⬇️ Download Excel",
        data=buf.getvalue(),
        file_name="cleaned_leads.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
