"""
Compare the most-recent City of Toronto shelter census scrape against our
published daily_occupancy.json and report any column-level discrepancies.

Reads:
  data/city_daily_table.json   — produced by validate_city_page.py
  data/daily_occupancy.json    — produced by generate_daily_occupancy.py

Outputs:
  data/city_audit_report.json  — machine-readable report
  data/city_audit_summary.md   — markdown summary (also printed to stdout)

The audit always exits 0 — it is a report, not a build gate.

Usage:
    python3 scripts/audit_city_scrape.py [YYYY-MM-DD]

If a date is omitted the most recent date present in both sources is used.

Author: Miriam Marling <miriam@BonQuery.ca>
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR         = Path(__file__).parent.parent / "data"
CITY_TABLE_FILE  = DATA_DIR / "city_daily_table.json"
OCCUPANCY_FILE   = DATA_DIR / "daily_occupancy.json"
REPORT_FILE      = DATA_DIR / "city_audit_report.json"
SUMMARY_FILE     = DATA_DIR / "city_audit_summary.md"

# Pairs of (city column, our column) to compare.
COLUMN_PAIRS = [
    ("city_ind",   "ind",   "individuals"),
    ("city_occ",   "occ",   "occupied"),
    ("city_unocc", "unocc", "unoccupied"),
    ("city_cap",   "cap",   "actual capacity"),
    ("city_rate",  "rate",  "occupancy rate"),
]


def normalise(value):
    """Normalise values for comparison: collapse nulls, unify int/float repr."""
    if value is None:
        return ""
    s = str(value).strip()
    if s in ("", "NA", "N/A", "NaN", "nan", "null", "NULL", "None"):
        return ""
    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
        return repr(round(f, 4))
    except (ValueError, TypeError):
        return s


def fmt(value, col_name):
    """Human-readable value with commas for large numbers."""
    if value is None:
        return "—"
    if col_name == "city_rate":
        return f"{value:.1f}%"
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def load_city_table(date_arg=None):
    """Return (date_str, list_of_rows) from city_daily_table.json.

    If date_arg is given, use that date; otherwise use the most recent entry.
    Returns (None, []) if the file is missing or the date is not found.
    """
    if not CITY_TABLE_FILE.exists():
        print(f"city_daily_table.json not found — has validate_city_page.py run yet?",
              file=sys.stderr)
        return None, []
    try:
        payload = json.loads(CITY_TABLE_FILE.read_text())
    except Exception as exc:
        print(f"Failed to parse city_daily_table.json: {exc}", file=sys.stderr)
        return None, []

    entries = payload.get("entries", {})
    if not entries:
        print("city_daily_table.json has no entries yet.", file=sys.stderr)
        return None, []

    if date_arg:
        rows = entries.get(date_arg)
        if rows is None:
            print(f"Date {date_arg} not found in city_daily_table.json. "
                  f"Available: {sorted(entries)[-5:]}", file=sys.stderr)
            return None, []
        return date_arg, rows

    latest = sorted(entries)[-1]
    return latest, entries[latest]


def load_our_rows(date_str):
    """Return {key: row_dict} for date_str from daily_occupancy.json."""
    if not OCCUPANCY_FILE.exists():
        print("daily_occupancy.json not found.", file=sys.stderr)
        return {}
    try:
        all_rows = json.loads(OCCUPANCY_FILE.read_text())
    except Exception as exc:
        print(f"Failed to parse daily_occupancy.json: {exc}", file=sys.stderr)
        return {}
    return {r["key"]: r for r in all_rows if r.get("date") == date_str}


def run_audit(city_date, city_rows, our_rows):
    """Compare city_rows vs our_rows; return list of mismatch dicts."""
    mismatches = []
    for city_row in city_rows:
        key   = city_row["key"]
        label = city_row["label"]
        our   = our_rows.get(key)

        for city_col, our_col, col_label in COLUMN_PAIRS:
            city_val = city_row.get(city_col)
            our_val  = our.get(our_col) if our else None

            # Both null → no opinion; skip
            if city_val is None and our_val is None:
                continue
            # One null and the other not → only flag if the City published a value
            # but we have nothing (gaps in our data). Skip if City is null (summary row).
            if city_val is None:
                continue

            if normalise(city_val) != normalise(our_val):
                try:
                    delta = round(float(city_val) - float(our_val), 4) \
                        if our_val is not None else None
                except (TypeError, ValueError):
                    delta = None

                mismatches.append({
                    "key":       key,
                    "label":     label,
                    "column":    col_label,
                    "city_col":  city_col,
                    "our_col":   our_col,
                    "city_val":  city_val,
                    "our_val":   our_val,
                    "delta":     delta,
                })

    return mismatches


def build_markdown(city_date, our_date, city_rows, mismatches, generated_at):
    """Return a markdown summary string."""
    n_rows     = len(city_rows)
    n_mismatches = len(mismatches)
    status     = "✅ all clear" if n_mismatches == 0 else f"⚠️ {n_mismatches} mismatch(es)"

    lines = [
        f"## City vs BonQuery Audit — {city_date}",
        "",
        f"**Status:** {status}  ",
        f"**City scrape date:** {city_date}  ",
        f"**Our latest date:** {our_date or '(unknown)'}  ",
        f"**Sectors compared:** {n_rows}  ",
        f"**Generated:** {generated_at}",
        "",
    ]

    if n_mismatches == 0:
        lines.append("All sectors and columns match the City's published figures.")
    else:
        lines += [
            "| Sector | Column | City | Ours | Delta |",
            "|--------|--------|------|------|-------|",
        ]
        for m in mismatches:
            city_fmt  = fmt(m["city_val"], m["city_col"])
            our_fmt   = fmt(m["our_val"],  m["our_col"])
            delta_fmt = (
                f"{m['delta']:+,.1f}" if m["delta"] is not None else "—"
            )
            lines.append(
                f"| {m['label']} | {m['column']} | {city_fmt} | {our_fmt} "
                f"| {delta_fmt} |"
            )
        lines += [
            "",
            "_Delta = City − Ours. Positive means the City reports higher than we do._",
        ]

    return "\n".join(lines)


def main():
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None

    city_date, city_rows = load_city_table(date_arg)
    if city_date is None:
        # Nothing to audit — write an empty report and exit cleanly
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "city_date":    None,
            "our_date":     None,
            "note":         "No City scrape data available for audit.",
            "passed":       None,
            "mismatch_count": 0,
            "mismatches":   [],
        }
        REPORT_FILE.write_text(json.dumps(payload, indent=2))
        print("audit_city_scrape: no City scrape data available; skipping.")
        sys.exit(0)

    our_rows = load_our_rows(city_date)
    our_date = city_date if our_rows else None

    if not our_rows:
        # Try the most recent date we have
        try:
            all_rows = json.loads(OCCUPANCY_FILE.read_text())
            dates = sorted({r["date"] for r in all_rows if r.get("date")}, reverse=True)
            our_date = dates[0] if dates else None
        except Exception:
            our_date = None
        print(
            f"No rows in daily_occupancy.json for {city_date}. "
            f"Our latest date: {our_date}. Audit skipped.",
            file=sys.stderr,
        )

    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    mismatches   = run_audit(city_date, city_rows, our_rows) if our_rows else []
    passed       = len(mismatches) == 0 if our_rows else None

    # ── Markdown summary ──────────────────────────────────────────────────────
    md = build_markdown(city_date, our_date, city_rows, mismatches, generated_at)
    print(md)
    SUMMARY_FILE.write_text(md + "\n")  # trailing newline keeps EOF on its own line

    # ── JSON report ───────────────────────────────────────────────────────────
    report = {
        "generated_at":   generated_at,
        "city_date":      city_date,
        "our_date":       our_date,
        "sectors_compared": len(city_rows),
        "passed":         passed,
        "mismatch_count": len(mismatches),
        "mismatches":     mismatches,
    }
    REPORT_FILE.write_text(json.dumps(report, indent=2))
    print(
        f"\ncity_audit_report.json: {len(mismatches)} mismatch(es) "
        f"for {city_date} ({len(city_rows)} sectors compared)"
    )


if __name__ == "__main__":
    main()
