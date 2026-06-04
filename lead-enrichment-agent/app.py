"""Lead Enrichment Agent — Streamlit UI."""

import io
import zipfile
import pandas as pd
import streamlit as st

from modules import salesnav, airscale as airscale_mod, cleaner, exporter, gsheets

st.set_page_config(
    page_title="Lead Enrichment Agent",
    page_icon="🎯",
    layout="wide",
)

# ── Styles ────────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    .step-header { font-size: 1.3rem; font-weight: 700; color: #4f8ef7; margin-bottom: 0.2rem; }
    .step-sub   { color: #888; font-size: 0.9rem; margin-bottom: 1rem; }
    .stProgress > div > div { background-color: #4f8ef7; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Session state ─────────────────────────────────────────────────────────────
def _init():
    defaults = {
        "step": 1,
        "raw_df": None,
        "enriched_df": None,
        "final_sheets": None,
        "sheet_url": "",
        "worksheet_index": 0,
        "import_mode": "file",   # "file" | "gsheet"
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init()


def go(step: int):
    st.session_state.step = step


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ Navigation")
    st.divider()
    steps = ["1. Import", "2. Enrich", "3. Clean", "4. Segment", "5. Export"]
    for i, label in enumerate(steps, 1):
        style = "**→ " + label + "**" if st.session_state.step == i else label
        st.markdown(style)

    st.divider()
    st.caption("API Keys")
    airscale_key = st.text_input("Airscale API Key", type="password", key="airscale_api_key")
    sa_json = st.text_area(
        "Google Service Account JSON",
        height=120,
        key="sa_json",
        help="Paste the full contents of your service-account credentials JSON file.",
    )


# ── Header ────────────────────────────────────────────────────────────────────
st.title("🎯 Lead Enrichment Agent")
progress_pct = (st.session_state.step - 1) / 4
st.progress(progress_pct)
st.caption(f"Step {st.session_state.step} of 5")
st.divider()


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — Import leads
# ══════════════════════════════════════════════════════════════════════════════
if st.session_state.step == 1:
    st.markdown('<p class="step-header">Step 1 — Import Leads</p>', unsafe_allow_html=True)

    import_tab, gsheet_tab = st.tabs(["📂 Upload File", "📊 Google Sheet"])

    # ── File upload ───────────────────────────────────────────────────────────
    with import_tab:
        st.markdown(
            '<p class="step-sub">Upload a CSV or Excel export from Sales Navigator or any other source.</p>',
            unsafe_allow_html=True,
        )
        uploaded = st.file_uploader(
            "Upload leads file (CSV or Excel)",
            type=["csv", "xlsx", "xls"],
        )
        if uploaded:
            if st.button("Load File →", type="primary"):
                with st.spinner("Parsing file…"):
                    try:
                        df = salesnav.parse_file(uploaded)
                        st.session_state.raw_df = df
                        st.session_state.import_mode = "file"
                        st.success(f"Loaded {len(df)} leads.")
                        st.dataframe(df.head(8), use_container_width=True)
                        go(2)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error reading file: {e}")

    # ── Google Sheet ──────────────────────────────────────────────────────────
    with gsheet_tab:
        st.markdown(
            '<p class="step-sub">Pull the dashboard registrant sheet directly. '
            'Rows with a missing <b>Enriched Business Email</b> will be auto-selected for enrichment.</p>',
            unsafe_allow_html=True,
        )

        sheet_url = st.text_input(
            "Google Sheet URL",
            value=st.session_state.sheet_url,
            placeholder="https://docs.google.com/spreadsheets/d/…",
        )
        worksheet_index = st.number_input(
            "Worksheet tab (0 = first tab)", min_value=0, value=0, step=1
        )

        if not sa_json:
            st.info("Paste your Google Service Account JSON in the sidebar to connect.")

        if st.button("Pull from Google Sheet →", type="primary", disabled=not (sheet_url and sa_json)):
            with st.spinner("Connecting to Google Sheets…"):
                try:
                    df = gsheets.read_sheet(sheet_url, sa_json, int(worksheet_index))
                    st.session_state.raw_df = df
                    st.session_state.sheet_url = sheet_url
                    st.session_state.worksheet_index = int(worksheet_index)
                    st.session_state.import_mode = "gsheet"

                    needs = int(df["needs_enrichment"].sum()) if "needs_enrichment" in df.columns else "?"
                    st.success(
                        f"Loaded **{len(df)} leads** — **{needs}** missing business email (will be enriched)."
                    )
                    st.dataframe(
                        df.drop(columns=["_sheet_row", "needs_enrichment"], errors="ignore").head(10),
                        use_container_width=True,
                    )
                    go(2)
                    st.rerun()
                except Exception as e:
                    st.error(f"Could not read sheet: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — Enrichment
# ══════════════════════════════════════════════════════════════════════════════
elif st.session_state.step == 2:
    st.markdown('<p class="step-header">Step 2 — Enrich with Airscale</p>', unsafe_allow_html=True)

    df = st.session_state.raw_df
    needs_col = df.get("needs_enrichment", pd.Series([True] * len(df)))
    missing_count = int(needs_col.sum())
    total = len(df)

    st.info(
        f"**{total} total leads** — **{missing_count}** missing business email and will be sent to Airscale."
    )

    auto_tab, manual_tab = st.tabs(["⚡ Auto-Enrich via API", "🖥️ Manual (upload Airscale result)"])

    # ── Auto enrichment ───────────────────────────────────────────────────────
    with auto_tab:
        st.markdown(
            '<p class="step-sub">Send leads with missing business email directly to the Airscale API.</p>',
            unsafe_allow_html=True,
        )

        if not airscale_key:
            st.info("Enter your Airscale API key in the sidebar to enable auto-enrichment.")

        st.subheader("Enrichment fields")
        selected_fields: list[str] = []
        cols = st.columns(3)
        for i, (field, (desc, default)) in enumerate(airscale_mod.AVAILABLE_ENRICHMENTS.items()):
            checked = cols[i % 3].checkbox(f"`{field}` — {desc}", value=default, key=f"field_{field}")
            if checked:
                selected_fields.append(field)

        only_missing = st.checkbox(
            "Only enrich leads with missing business email (recommended)", value=True
        )

        col1, col2 = st.columns([1, 5])
        col1.button("← Back", on_click=go, args=(1,))

        if col2.button(
            f"Enrich {missing_count if only_missing else total} leads →",
            type="primary",
            disabled=not (airscale_key and selected_fields),
        ):
            enrich_df = df[df["needs_enrichment"]].copy() if only_missing else df.copy()

            with st.spinner(f"Sending {len(enrich_df)} leads to Airscale…"):
                try:
                    enriched_chunk = airscale_mod.enrich(enrich_df, selected_fields, airscale_key)

                    result = df.copy()
                    if only_missing:
                        result.loc[enrich_df.index, enriched_chunk.columns] = enriched_chunk.values
                    else:
                        result = enriched_chunk

                    be = result.get("business_email", pd.Series(dtype=str))
                    result["needs_enrichment"] = be.isna() | (be.astype(str).str.strip() == "")

                    st.session_state.enriched_df = result
                    filled = int((~result["needs_enrichment"]).sum())
                    st.success(f"Done. **{filled}/{total}** leads now have a business email.")
                    st.dataframe(
                        result.drop(columns=["_sheet_row", "needs_enrichment"], errors="ignore").head(10),
                        use_container_width=True,
                    )
                    go(3)
                    st.rerun()
                except Exception as e:
                    st.error(f"Airscale error: {e}")

    # ── Manual upload ─────────────────────────────────────────────────────────
    with manual_tab:
        st.markdown(
            '<p class="step-sub">Download raw leads, enrich on airscale.io, then upload the result here.</p>',
            unsafe_allow_html=True,
        )

        clean_df = df.drop(columns=["_sheet_row", "needs_enrichment"], errors="ignore")
        raw_csv = clean_df.to_csv(index=False).encode("utf-8")
        raw_xlsx = exporter.to_excel({"Leads": clean_df})

        dl1, dl2 = st.columns(2)
        dl1.download_button("⬇️ Download CSV for Airscale", data=raw_csv,
                            file_name="leads_for_airscale.csv", mime="text/csv")
        dl2.download_button("⬇️ Download Excel for Airscale", data=raw_xlsx,
                            file_name="leads_for_airscale.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        with st.expander("Airscale step-by-step instructions"):
            st.markdown(
                """
1. Go to **airscale.io** and log in
2. Create a new list → **Import CSV** → upload the file above
3. Select enrichment fields → run enrichment → wait for completion
4. **Export / Download** the enriched list as CSV or Excel
5. Upload it below
"""
            )

        st.divider()
        enriched_upload = st.file_uploader(
            "Upload Airscale-enriched CSV or Excel",
            type=["csv", "xlsx", "xls"],
            key="airscale_manual_upload",
        )

        col1, col2, col3 = st.columns([1, 2, 3])
        col1.button("← Back", on_click=go, args=(1,), key="back_manual")

        if enriched_upload:
            if col2.button("Load Enriched File →", type="primary"):
                try:
                    name = enriched_upload.name.lower()
                    enriched_df = pd.read_csv(enriched_upload) if name.endswith(".csv") else pd.read_excel(enriched_upload)
                    enriched_df = salesnav._normalize_columns(enriched_df)
                    enriched_df = enriched_df.reset_index(drop=True)
                    base = df.reset_index(drop=True)
                    for col in enriched_df.columns:
                        if col not in base.columns:
                            base[col] = enriched_df[col]
                        else:
                            mask = base[col].isna() | (base[col].astype(str).str.strip() == "")
                            base.loc[mask, col] = enriched_df.loc[mask, col]
                    st.session_state.enriched_df = base
                    st.success(f"✅ {len(base)} enriched leads loaded.")
                    st.dataframe(
                        base.drop(columns=["_sheet_row", "needs_enrichment"], errors="ignore").head(8),
                        use_container_width=True,
                    )
                    go(3)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error loading file: {e}")

        if col3.button("Skip — use raw data as-is"):
            st.session_state.enriched_df = df.copy()
            go(3)
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — Clean
# ══════════════════════════════════════════════════════════════════════════════
elif st.session_state.step == 3:
    st.markdown('<p class="step-header">Step 3 — Clean the Data</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="step-sub">Set your cleaning rules. The agent will apply them to all leads.</p>',
        unsafe_allow_html=True,
    )

    df = st.session_state.enriched_df
    visible = df.drop(columns=["_sheet_row", "needs_enrichment"], errors="ignore")
    st.info(f"{len(df)} leads | {len(visible.columns)} columns")

    col_a, col_b = st.columns(2)
    drop_no_email = col_a.checkbox("Drop leads with no email", value=False)
    drop_no_phone = col_b.checkbox("Drop leads with no phone", value=False)
    title_case = col_a.checkbox("Title-case names", value=True)
    dedup_on = st.multiselect(
        "Deduplicate on these columns (keep first occurrence)",
        options=visible.columns.tolist(),
        default=["linkedin_url"] if "linkedin_url" in visible.columns else [],
    )

    st.divider()
    col1, col2 = st.columns([1, 5])
    col1.button("← Back", on_click=go, args=(2,))

    if col2.button("Apply Cleaning →", type="primary"):
        with st.spinner("Cleaning…"):
            cleaned = cleaner.clean(
                df,
                drop_missing_email=drop_no_email,
                drop_missing_phone=drop_no_phone,
                dedupe_on=dedup_on if dedup_on else None,
                title_case_names=title_case,
            )
            st.session_state.enriched_df = cleaned
            st.success(f"Cleaned. {len(cleaned)} leads remain.")
            st.dataframe(
                cleaned.drop(columns=["_sheet_row", "needs_enrichment"], errors="ignore").head(10),
                use_container_width=True,
            )
            go(4)
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — Segment
# ══════════════════════════════════════════════════════════════════════════════
elif st.session_state.step == 4:
    st.markdown('<p class="step-header">Step 4 — Segment the List</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="step-sub">How would you like to split or organize the final output?</p>',
        unsafe_allow_html=True,
    )

    df = st.session_state.enriched_df
    visible_cols = df.drop(columns=["_sheet_row", "needs_enrichment"], errors="ignore").columns.tolist()

    segment_mode = st.radio(
        "Segmentation mode",
        options=[
            "Single list (no split)",
            "Split by column value (one tab/file per group)",
        ],
    )

    sheets: dict[str, pd.DataFrame] = {}

    if segment_mode == "Single list (no split)":
        sheet_name = st.text_input("Sheet / file name", value="Leads")
        sheets = {sheet_name: df}
    else:
        seg_col = st.selectbox(
            "Split by which column?",
            options=visible_cols,
            index=visible_cols.index("company_industry") if "company_industry" in visible_cols else 0,
        )
        if seg_col:
            preview_groups = df[seg_col].value_counts()
            st.write(f"**Preview — {len(preview_groups)} groups:**")
            st.dataframe(preview_groups.rename("count").reset_index(), use_container_width=True)
            sheets = cleaner.segment(df, seg_col)

    st.divider()
    col1, col2 = st.columns([1, 5])
    col1.button("← Back", on_click=go, args=(3,))

    if col2.button("Build Output →", type="primary"):
        st.session_state.final_sheets = sheets
        go(5)
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# STEP 5 — Export
# ══════════════════════════════════════════════════════════════════════════════
elif st.session_state.step == 5:
    st.markdown('<p class="step-header">Step 5 — Export</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="step-sub">Download the enriched list and/or write it back to the Google Sheet.</p>',
        unsafe_allow_html=True,
    )

    sheets = st.session_state.final_sheets
    enriched_df = st.session_state.enriched_df
    total_leads = sum(len(v) for v in sheets.values())

    st.success(f"✅ Ready — **{total_leads} leads** across **{len(sheets)} sheet(s)**")

    summary = pd.DataFrame(
        [(name, len(df_)) for name, df_ in sheets.items()],
        columns=["Segment", "Leads"],
    )
    st.dataframe(summary, use_container_width=True, hide_index=True)

    st.divider()

    # ── Write back to Google Sheet ────────────────────────────────────────────
    if st.session_state.import_mode == "gsheet" and st.session_state.sheet_url:
        st.subheader("📊 Write back to Google Sheet")
        st.caption(
            "Updates only the **Enriched Business Email**, **Enriched Phone Number 1**, "
            "and **Enriched Phone Number 2** columns — all other data is untouched."
        )
        if not sa_json:
            st.info("Service Account JSON required in the sidebar.")
        else:
            if st.button("⬆️ Write enriched columns to Google Sheet", type="primary"):
                with st.spinner("Writing to Google Sheet…"):
                    try:
                        updated = gsheets.write_enriched_column(
                            st.session_state.sheet_url,
                            sa_json,
                            enriched_df,
                            st.session_state.worksheet_index,
                        )
                        st.success(f"Updated **{updated} cells** in the Google Sheet.")
                    except Exception as e:
                        st.error(f"Write failed: {e}")

        st.divider()

    # ── CSV for dashboard ─────────────────────────────────────────────────────
    st.subheader("📄 Dashboard CSV")
    if st.session_state.import_mode == "gsheet":
        dashboard_csv = gsheets.sheet_to_csv(enriched_df)
        st.download_button(
            label="⬇️ Download Dashboard CSV",
            data=dashboard_csv,
            file_name="dashboard_enriched.csv",
            mime="text/csv",
            type="primary",
        )
    else:
        csv_files = exporter.to_csv_zip(sheets)
        if len(csv_files) == 1:
            name, data = next(iter(csv_files.items()))
            st.download_button(
                label="⬇️ Download CSV",
                data=data,
                file_name=name,
                mime="text/csv",
                type="primary",
            )
        else:
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for fname, fdata in csv_files.items():
                    zf.writestr(fname, fdata)
            st.download_button(
                label="⬇️ Download CSVs (zip)",
                data=zip_buf.getvalue(),
                file_name="leads_enriched_csvs.zip",
                mime="application/zip",
            )

    st.divider()

    # ── Excel ─────────────────────────────────────────────────────────────────
    st.subheader("📊 Excel (.xlsx)")
    clean_sheets = {
        k: v.drop(columns=["_sheet_row", "needs_enrichment"], errors="ignore")
        for k, v in sheets.items()
    }
    with st.spinner("Building Excel file…"):
        xl_bytes = exporter.to_excel(clean_sheets)
    st.download_button(
        label="⬇️ Download Excel",
        data=xl_bytes,
        file_name="leads_enriched.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    st.divider()
    col1, col2 = st.columns([1, 5])
    col1.button("← Back", on_click=go, args=(4,))
    if col2.button("🔄 Start Over"):
        for key in ["raw_df", "enriched_df", "final_sheets", "sheet_url"]:
            st.session_state[key] = None
        st.session_state["import_mode"] = "file"
        go(1)
        st.rerun()
