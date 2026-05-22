"""
One-shot: convert the sibling repo's 2026-05-17 raw CKAN CSV into our
standard snapshot format (gzipped JSON in data/snapshots/) so it can be
diffed against later pulls.

The source CSV lives outside this repo and is untouched. We just register
it as our earliest per-location baseline at:

    data/snapshots/raw_2026-05-17T0000Z.json.gz

After this runs once, the diff script can compare any later snapshot against
this baseline.

Author: Miriam Marling <miriam@BonQuery.ca>
"""

import csv
import gzip
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SOURCE_CSV = Path(
    "/Users/Atom/projects/toronto-shelter-db/analysis/data/"
    "daily_occupancy/daily_occupancy_raw_2026-05-17.csv"
)
OUT_DIR    = Path(__file__).parent.parent / "data" / "snapshots"
# Timestamp the snapshot at the start of 2026-05-17 UTC. The exact wall-clock
# moment when this file was pulled isn't recorded; using 00:00Z keeps it sorted
# before any later same-day pulls and is honest about the date-level precision.
PULLED_AT  = datetime(2026, 5, 17, 0, 0, 0, tzinfo=timezone.utc)

SCHEMA_VERSION = 1


def main():
    if not SOURCE_CSV.exists():
        sys.exit(f"Baseline CSV not found at {SOURCE_CSV}")

    print(f"Reading {SOURCE_CSV} ...", flush=True)
    with open(SOURCE_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print(f"  {len(rows):,} rows loaded")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = PULLED_AT.strftime("%Y-%m-%dT%H%M%SZ")
    path = OUT_DIR / f"raw_{stamp}.json.gz"

    payload = {
        "schema_version": SCHEMA_VERSION,
        "pulled_at":      PULLED_AT.isoformat().replace("+00:00", "Z"),
        "source":         "imported-baseline-csv",
        "source_path":    str(SOURCE_CSV),
        "package_id":     "daily-shelter-overnight-service-occupancy-capacity",
        "row_count":      len(rows),
        "rows":           rows,
    }
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"))
    print(f"Wrote {path} ({path.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
