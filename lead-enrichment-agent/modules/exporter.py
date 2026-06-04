"""Export enriched data to Excel and CSV."""

import io
import pandas as pd


def to_excel(sheets: dict[str, pd.DataFrame]) -> bytes:
    """
    Write one or more dataframes to an Excel workbook.
    sheets: {"Sheet Name": dataframe, ...}
    Returns bytes of the .xlsx file.
    """
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        for sheet_name, df in sheets.items():
            safe_name = _safe_sheet_name(sheet_name)
            df.to_excel(writer, sheet_name=safe_name, index=False)
            _format_sheet(writer, safe_name, df)
    return buf.getvalue()


def to_csv_zip(sheets: dict[str, pd.DataFrame]) -> dict[str, bytes]:
    """Return a dict of {filename: csv_bytes} for each sheet."""
    result = {}
    for name, df in sheets.items():
        result[f"{name}.csv"] = df.to_csv(index=False).encode("utf-8")
    return result


def _safe_sheet_name(name: str) -> str:
    """Excel sheet names max 31 chars, no special chars."""
    safe = "".join(c if c.isalnum() or c in (" ", "_", "-") else "_" for c in str(name))
    return safe[:31]


def _format_sheet(writer: pd.ExcelWriter, sheet_name: str, df: pd.DataFrame):
    """Auto-fit column widths and freeze the header row."""
    workbook = writer.book
    worksheet = writer.sheets[sheet_name]

    header_fmt = workbook.add_format(
        {"bold": True, "bg_color": "#1a1a2e", "font_color": "#ffffff", "border": 1}
    )
    row_fmt = workbook.add_format({"border": 1})

    for col_num, col_name in enumerate(df.columns):
        max_len = max(
            len(str(col_name)),
            df[col_name].astype(str).str.len().max() if len(df) > 0 else 0,
        )
        width = min(max_len + 2, 50)
        worksheet.set_column(col_num, col_num, width, row_fmt)
        worksheet.write(0, col_num, col_name, header_fmt)

    worksheet.freeze_panes(1, 0)
    worksheet.autofilter(0, 0, len(df), len(df.columns) - 1)
