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

If a date is omitted all dates currently displayed on the City page are audited.

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
    if col_name in ("city_rate", "rate"):
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


def load_city_dates():
    """Return (payload_dict, sorted_dates_to_audit) from city_daily_table.json.

    Uses payload["last_scraped"] (dates currently displayed on the City page)
    if present; falls back to all entries for files written before that field
    was added.  Returns ({}, []) if the file is missing or unparseable.
    """
    if not CITY_TABLE_FILE.exists():
        print("city_daily_table.json not found — has validate_city_page.py "
              "run yet?", file=sys.stderr)
        return {}, []
    try:
        payload = json.loads(CITY_TABLE_FILE.read_text())
    except Exception as exc:
        print(f"Failed to parse city_daily_table.json: {exc}", file=sys.stderr)
        return {}, []

    entries = payload.get("entries", {})
    if not entries:
        print("city_daily_table.json has no entries yet.", file=sys.stderr)
        return payload, []

    last_scraped = payload.get("last_scraped")
    if last_scraped:
        dates = sorted(last_scraped)
    else:
        # Older file without last_scraped — fall back to all entries
        dates = sorted(entries)

    return payload, dates


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


def build_section(city_date, our_latest_date, city_rows, mismatches,
                  generated_at, status):
    """Return a markdown section string for one audit date.

    status is one of: "pass" | "fail" | "pending"
    """
    n_rows       = len(city_rows)
    n_mismatches = len(mismatches)

    if status == "pending":
        status_line = f"⏳ Pending — awaiting CKAN data for {city_date}"
    elif n_mismatches == 0:
        status_line = "✅ All clear"
    else:
        status_line = f"⚠️ {n_mismatches} mismatch(es)"

    lines = [
        f"### City vs BonQuery Audit — {city_date}",
        "",
        f"**Status:** {status_line}  ",
        f"**City scrape date:** {city_date}  ",
        f"**Our latest date:** {our_latest_date or '(unknown)'}  ",
        f"**Sectors compared:** {0 if status == 'pending' else n_rows}  ",
        f"**Generated:** {generated_at}",
        "",
    ]

    if status == "pending":
        lines.append(
            "The City has published figures for this date but "
            "our `daily_occupancy.json` does not yet contain it. "
            "Re-run after the next CKAN refresh."
        )
    elif n_mismatches == 0:
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


def _write_empty_report(generated_at):
    """Write a no-data report and print a notice."""
    payload = {
        "generated_at":    generated_at,
        "dates":           [],
        "total_mismatches": 0,
        "any_pending":     False,
        # Legacy fields kept for backward-compat with CI audit_check step
        "city_date":       None,
        "audit_date":      None,
        "our_date":        None,
        "note":            "No City scrape data available for audit.",
        "passed":          None,
        "mismatch_count":  0,
        "mismatches":      [],
    }
    REPORT_FILE.write_text(json.dumps(payload, indent=2))
    print("audit_city_scrape: no City scrape data available; skipping.")


def main():
    date_arg     = sys.argv[1] if len(sys.argv) > 1 else None
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    # ── Load our occupancy data once ──────────────────────────────────────────
    try:
        all_our_rows = (json.loads(OCCUPANCY_FILE.read_text())
                        if OCCUPANCY_FILE.exists() else [])
    except Exception as exc:
        print(f"Failed to parse daily_occupancy.json: {exc}", file=sys.stderr)
        all_our_rows = []
    our_date_set = {r["date"] for r in all_our_rows if r.get("date")}
    our_latest   = max(our_date_set) if our_date_set else None

    # ── Determine which dates to audit ───────────────────────────────────────
    if date_arg:
        city_date, city_rows = load_city_table(date_arg)
        if city_date is None:
            _write_empty_report(generated_at)
            sys.exit(0)
        try:
            payload = json.loads(CITY_TABLE_FILE.read_text())
        except Exception:
            payload = {"entries": {date_arg: city_rows}}
        dates_to_audit = [date_arg]
    else:
        payload, dates_to_audit = load_city_dates()
        if not dates_to_audit:
            _write_empty_report(generated_at)
            sys.exit(0)

    entries = payload.get("entries", {})

    # ── Audit each date ───────────────────────────────────────────────────────
    date_results = []
    for audit_date in dates_to_audit:
        city_rows = entries.get(audit_date, [])
        if not city_rows:
            print(f"  {audit_date}: no city rows in entries — skipping",
                  file=sys.stderr)
            continue

        our_rows = {r["key"]: r for r in all_our_rows
                    if r.get("date") == audit_date}

        if not our_rows:
            status     = "pending"
            mismatches = []
            print(f"  {audit_date}: pending (no BonQuery data yet)")
        else:
            mismatches = run_audit(audit_date, city_rows, our_rows)
            status     = "pass" if not mismatches else "fail"
            print(f"  {audit_date}: {status} ({len(mismatches)} mismatch(es))")

        date_results.append({
            "date":       audit_date,
            "status":     status,
            "city_rows":  city_rows,
            "mismatches": mismatches,
        })

    if not date_results:
        _write_empty_report(generated_at)
        sys.exit(0)

    # ── Build markdown (one section per date) ─────────────────────────────────
    sections = [
        build_section(
            dr["date"], our_latest, dr["city_rows"],
            dr["mismatches"], generated_at, dr["status"],
        )
        for dr in date_results
    ]
    md = "\n\n---\n\n".join(sections)
    print(md)
    SUMMARY_FILE.write_text(md + "\n")

    # ── JSON report ───────────────────────────────────────────────────────────
    total_mismatches = sum(len(dr["mismatches"]) for dr in date_results)
    any_pending      = any(dr["status"] == "pending" for dr in date_results)

    dates_entry = [
        {
            "date":             dr["date"],
            "status":           dr["status"],
            "passed":           (True  if dr["status"] == "pass"
                                 else False if dr["status"] == "fail"
                                 else None),
            "pending":          dr["status"] == "pending",
            "sectors_compared": (0 if dr["status"] == "pending"
                                 else len(dr["city_rows"])),
            "mismatch_count":   len(dr["mismatches"]),
            "mismatches":       dr["mismatches"],
        }
        for dr in date_results
    ]

    latest_date = date_results[-1]["date"]
    report = {
        "generated_at":    generated_at,
        "dates":           dates_entry,
        "total_mismatches": total_mismatches,
        "any_pending":     any_pending,
        # Legacy fields — kept for backward-compat with the audit_check CI step
        "city_date":       latest_date,
        "audit_date":      latest_date,
        "our_date":        our_latest,
        "mismatch_count":  total_mismatches,
        "passed":          total_mismatches == 0 and not any_pending,
        "mismatches":      date_results[-1]["mismatches"],
    }
    REPORT_FILE.write_text(json.dumps(report, indent=2))
    print(
        f"\ncity_audit_report.json: {total_mismatches} total mismatch(es) "
        f"across {len(date_results)} date(s)"
        + (f" ({sum(1 for d in date_results if d['status'] == 'pending')} pending)"
           if any_pending else "")
    )


if __name__ == "__main__":
    main()
