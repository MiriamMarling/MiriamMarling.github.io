"""
Diff two CKAN raw snapshots (gzipped JSON, written by generate_daily_occupancy.py
or import_baseline_snapshot.py) and produce a structured drift report.

Row identity is keyed on (PROGRAM_ID, OCCUPANCY_DATE). The report separates
three classes of change:

  - added   — (PROGRAM_ID, date) present in NEW snapshot but not OLD
              (the "missing-then-added" hypothesis)
  - removed — (PROGRAM_ID, date) present in OLD but not NEW
              (rare; means CKAN dropped a previously published row)
  - changed — same key in both, but field values differ
              (the "present-then-revised" hypothesis)

Usage:
    python3 scripts/diff_ckan_snapshots.py [OLD_SNAPSHOT] [NEW_SNAPSHOT]

If paths are omitted, the two most-recent snapshots in data/snapshots/ are used.

Output: data/ckan_drift_report.json

Author: Miriam Marling <miriam@BonQuery.ca>
"""

import argparse
import gzip
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR      = Path(__file__).parent.parent / "data"
SNAPSHOTS_DIR = DATA_DIR / "snapshots"
REPORT_PATH   = DATA_DIR / "ckan_drift_report.json"

# Numeric / value fields whose changes matter operationally.
COMPARE_FIELDS = [
    "SERVICE_USER_COUNT",
    "OCCUPIED_BEDS", "UNOCCUPIED_BEDS", "UNAVAILABLE_BEDS",
    "CAPACITY_ACTUAL_BED", "CAPACITY_FUNDING_BED",
    "OCCUPIED_ROOMS", "UNOCCUPIED_ROOMS", "UNAVAILABLE_ROOMS",
    "CAPACITY_ACTUAL_ROOM", "CAPACITY_FUNDING_ROOM",
    "OCCUPANCY_RATE_BEDS", "OCCUPANCY_RATE_ROOMS",
]

# Identity / labelling fields to include in the report for human readability.
LABEL_FIELDS = [
    "ORGANIZATION_NAME", "SHELTER_GROUP", "LOCATION_NAME",
    "PROGRAM_NAME", "SECTOR", "PROGRAM_MODEL", "OVERNIGHT_SERVICE_TYPE",
    "CAPACITY_TYPE",
]


def load_snapshot(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        payload = json.load(f)
    return payload


def normalise_date(value):
    """Reduce date-or-datetime strings to YYYY-MM-DD.

    The live CKAN dump emits ISO datetimes like '2026-05-14T00:00:00';
    the archived May 17 CSV was post-processed to plain dates like
    '2026-05-14'. Both must collapse to the same key.
    """
    if value is None:
        return ""
    s = str(value).strip()
    if "T" in s:
        s = s.split("T", 1)[0]
    return s


def index_rows(rows):
    """Build a dict keyed on (PROGRAM_ID, OCCUPANCY_DATE) → row.

    OCCUPANCY_DATE is normalised so 'YYYY-MM-DD' and 'YYYY-MM-DDT00:00:00'
    collapse to the same key.
    """
    by_key = {}
    for r in rows:
        pid  = str(r.get("PROGRAM_ID", "")).strip()
        date = normalise_date(r.get("OCCUPANCY_DATE", ""))
        if pid and date:
            by_key[(pid, date)] = r
    return by_key


NULL_SENTINELS = {"", "NA", "N/A", "n/a", "NaN", "nan", "null", "NULL", "None"}


def normalise(value):
    """Normalise CKAN field values for comparison across snapshots.

    Different snapshot sources represent missing data differently — the live
    CKAN dump uses '', while CSVs that have round-tripped through R encode
    null as 'NA'. We also need '83' == '83.0' for numeric fields.
    """
    if value is None:
        return ""
    s = str(value).strip()
    if s in NULL_SENTINELS:
        return ""
    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
        return repr(f)
    except (ValueError, TypeError):
        return s


def field_diff(old_row, new_row):
    """Return {FIELD: [old_value, new_value]} for any COMPARE_FIELDS that differ."""
    out = {}
    for f in COMPARE_FIELDS:
        a = normalise(old_row.get(f))
        b = normalise(new_row.get(f))
        if a != b:
            out[f] = [a, b]
    return out


def label_dict(row):
    return {f: row.get(f, "") for f in LABEL_FIELDS}


def two_most_recent_snapshots():
    snaps = sorted(SNAPSHOTS_DIR.glob("raw_*.json.gz"))
    if len(snaps) < 2:
        sys.exit(
            f"Need ≥2 snapshots in {SNAPSHOTS_DIR}; found {len(snaps)}. "
            "Run import_baseline_snapshot.py and/or generate_daily_occupancy.py first."
        )
    return snaps[-2], snaps[-1]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("old_snapshot", nargs="?", type=Path,
                    help="Path to OLD snapshot (.json.gz). Defaults to 2nd-newest in data/snapshots/.")
    ap.add_argument("new_snapshot", nargs="?", type=Path,
                    help="Path to NEW snapshot (.json.gz). Defaults to newest in data/snapshots/.")
    args = ap.parse_args()

    if args.old_snapshot is None or args.new_snapshot is None:
        old_path, new_path = two_most_recent_snapshots()
    else:
        old_path, new_path = args.old_snapshot, args.new_snapshot

    print(f"OLD: {old_path}")
    print(f"NEW: {new_path}")

    old_payload = load_snapshot(old_path)
    new_payload = load_snapshot(new_path)

    old_idx = index_rows(old_payload["rows"])
    new_idx = index_rows(new_payload["rows"])
    print(f"  OLD rows: {len(old_idx):,}")
    print(f"  NEW rows: {len(new_idx):,}")

    old_keys = set(old_idx)
    new_keys = set(new_idx)

    added_keys   = new_keys - old_keys
    removed_keys = old_keys - new_keys
    common_keys  = old_keys & new_keys

    changed = []
    for key in common_keys:
        diff = field_diff(old_idx[key], new_idx[key])
        if diff:
            changed.append((key, diff))

    print(f"  added:   {len(added_keys):,}")
    print(f"  removed: {len(removed_keys):,}")
    print(f"  changed: {len(changed):,}")

    # Group by OCCUPANCY_DATE
    by_date = defaultdict(lambda: {"added": [], "removed": [], "changed": []})

    for key in added_keys:
        prog_id, date = key
        row = new_idx[key]
        by_date[date]["added"].append({
            "PROGRAM_ID": prog_id,
            **label_dict(row),
        })

    for key in removed_keys:
        prog_id, date = key
        row = old_idx[key]
        by_date[date]["removed"].append({
            "PROGRAM_ID": prog_id,
            **label_dict(row),
        })

    for key, diff in changed:
        prog_id, date = key
        row = new_idx[key]
        by_date[date]["changed"].append({
            "PROGRAM_ID": prog_id,
            **label_dict(row),
            "field_changes": diff,
        })

    # Sort each list by PROGRAM_ID for stable output
    for d in by_date.values():
        d["added"].sort(key=lambda r: r["PROGRAM_ID"])
        d["removed"].sort(key=lambda r: r["PROGRAM_ID"])
        d["changed"].sort(key=lambda r: r["PROGRAM_ID"])

    # Per-date program counts (helps spot dates that grew or shrunk)
    for date in sorted(set(k[1] for k in old_keys) | set(k[1] for k in new_keys)):
        n_old = sum(1 for k in old_keys if k[1] == date)
        n_new = sum(1 for k in new_keys if k[1] == date)
        if n_old != n_new or date in by_date:
            by_date[date]["n_programs_old"] = n_old
            by_date[date]["n_programs_new"] = n_new

    report = {
        "old_snapshot": {
            "path":      str(old_path.name),
            "pulled_at": old_payload.get("pulled_at"),
            "row_count": old_payload.get("row_count", len(old_idx)),
        },
        "new_snapshot": {
            "path":      str(new_path.name),
            "pulled_at": new_payload.get("pulled_at"),
            "row_count": new_payload.get("row_count", len(new_idx)),
        },
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "summary": {
            "rows_total_old":   len(old_idx),
            "rows_total_new":   len(new_idx),
            "dates_in_old":     len({k[1] for k in old_keys}),
            "dates_in_new":     len({k[1] for k in new_keys}),
            "rows_added":       len(added_keys),
            "rows_removed":     len(removed_keys),
            "rows_changed":     len(changed),
            "dates_with_drift": sorted(by_date.keys()),
        },
        "by_date": dict(sorted(by_date.items())),
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"Wrote {REPORT_PATH} ({REPORT_PATH.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
