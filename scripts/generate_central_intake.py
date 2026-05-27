"""
Pulls City of Toronto Central Intake Calls data from CKAN, aggregates
monthly statistics, merges with daily occupancy data, and writes:
  data/central_intake.json

Resources consumed:
  - Central Intake Service Queue Data
    (resource_id: 61191143-8143-4425-bf89-2c1523961227)
  - Central Intake Call Wrap-Up Codes Data
    (resource_id: 9da03ed6-cd19-4df7-9b0a-03f81bf4995c)
  - data/daily_occupancy.json  (pre-generated; SERVICE_USER_COUNT aggregate)

No external dependencies beyond the Python standard library.

Author: Miriam Marling <miriam@BonQuery.ca>
Date: 2026
"""

import json
import math
import ssl
import urllib.request
from collections import defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CKAN_BASE = "https://ckan0.cf.opendata.inter.prod-toronto.ca"

# Datastore resource IDs (not the CSV/XML/JSON static-file variants).
SQ_RESOURCE_ID  = "61191143-8143-4425-bf89-2c1523961227"  # Service Queue
WUC_RESOURCE_ID = "9da03ed6-cd19-4df7-9b0a-03f81bf4995c"  # Wrap-Up Codes

# Required columns — script fails loudly if any are absent.
SQ_REQUIRED_COLS  = {"Date", "Unmatched callers"}
WUC_REQUIRED_COLS = {
    "Date",
    "Total calls handled",
    "Code 1A - Referral to a Sleeping/Resting Space",
}

OUT_DIR  = Path(__file__).parent.parent / "data"
OUT_JSON = OUT_DIR / "central_intake.json"
OCC_JSON = OUT_DIR / "daily_occupancy.json"

# The occupancy key whose `ind` field holds nightly SERVICE_USER_COUNT total.
OCC_KEY = "all_shelter"

# Permissive SSL context — needed on macOS where Python's CA bundle can be
# incomplete. On Linux (GitHub Actions ubuntu-latest) the system CAs work fine
# and this context is harmless.
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

# ---------------------------------------------------------------------------
# CKAN helpers
# ---------------------------------------------------------------------------

def ckan_datastore_all(resource_id, page_size=10000):
    """Fetch every row from a CKAN datastore resource via pagination."""
    rows = []
    offset = 0
    total = None

    while True:
        url = (
            f"{CKAN_BASE}/api/3/action/datastore_search"
            f"?resource_id={resource_id}"
            f"&limit={page_size}"
            f"&offset={offset}"
        )
        print(f"  GET {url.split('?')[0]} offset={offset} ...", flush=True)
        with urllib.request.urlopen(url, context=_SSL_CTX, timeout=60) as r:
            payload = json.loads(r.read().decode())

        result = payload["result"]
        if total is None:
            total = result["total"]
            print(f"  Total rows reported by API: {total:,}", flush=True)

        batch = result["records"]
        rows.extend(batch)

        if not batch or len(rows) >= total:
            break
        offset += page_size

    print(f"  Fetched {len(rows):,} rows total.", flush=True)
    return rows


def assert_columns(rows, required_cols, resource_label):
    """Fail loudly if any required column is missing from the data."""
    if not rows:
        raise ValueError(f"{resource_label}: no rows returned — cannot validate columns.")
    present = set(rows[0].keys())
    missing = required_cols - present
    if missing:
        raise ValueError(
            f"{resource_label}: required column(s) missing from data: "
            + ", ".join(sorted(missing))
            + f"\n  Columns present: {sorted(present)}"
        )


# ---------------------------------------------------------------------------
# Stats helpers
# ---------------------------------------------------------------------------

def to_float(v):
    """Parse a value to float, returning None if blank/null."""
    if v is None or v == "" or v == '""':
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def monthly_agg(values):
    """Return mean, sd, n, se for a list of numeric values (Nones excluded)."""
    clean = [v for v in values if v is not None]
    n = len(clean)
    if n == 0:
        return None, None, 0, None
    mean = sum(clean) / n
    # Population-style std dev when n==1 gives 0; use sample sd (ddof=1)
    # when n>1 to match typical reporting, matching R's default sd().
    if n == 1:
        sd = 0.0
    else:
        variance = sum((x - mean) ** 2 for x in clean) / (n - 1)
        sd = math.sqrt(variance)
    se = sd / math.sqrt(n)
    return round(mean, 4), round(sd, 4), n, round(se, 4)


MONTH_ABBR = [
    "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


# ---------------------------------------------------------------------------
# Pull and validate CKAN resources
# ---------------------------------------------------------------------------

def pull_service_queue():
    print("Pulling Service Queue Data ...", flush=True)
    rows = ckan_datastore_all(SQ_RESOURCE_ID)
    assert_columns(rows, SQ_REQUIRED_COLS, "Service Queue")
    # Remove internal CKAN _id column from output rows
    return [{k: v for k, v in row.items() if k != "_id"} for row in rows]


def pull_wrap_up_codes():
    print("Pulling Wrap-Up Codes Data ...", flush=True)
    rows = ckan_datastore_all(WUC_RESOURCE_ID)
    assert_columns(rows, WUC_REQUIRED_COLS, "Wrap-Up Codes")
    return [{k: v for k, v in row.items() if k != "_id"} for row in rows]


# ---------------------------------------------------------------------------
# Monthly aggregation — call/caller metrics
# ---------------------------------------------------------------------------

def agg_call_metrics(sq_rows, wuc_rows):
    """
    Build per-month statistics for three metrics:
      referred   <- Wrap-Up Codes "Code 1A - Referral to a Sleeping/Resting Space"
      handled    <- Wrap-Up Codes "Total calls handled"
      unmatched  <- Service Queue "Unmatched callers"

    Returns a dict keyed by (year, month) -> {referred:[...], handled:[...], unmatched:[...]}.
    """
    buckets = defaultdict(lambda: {"referred": [], "handled": [], "unmatched": []})

    for row in wuc_rows:
        date_str = row.get("Date", "")
        if not date_str or len(date_str) < 7:
            continue
        try:
            year, month = int(date_str[:4]), int(date_str[5:7])
        except ValueError:
            continue
        key = (year, month)
        buckets[key]["referred"].append(
            to_float(row.get("Code 1A - Referral to a Sleeping/Resting Space"))
        )
        buckets[key]["handled"].append(
            to_float(row.get("Total calls handled"))
        )

    for row in sq_rows:
        date_str = row.get("Date", "")
        if not date_str or len(date_str) < 7:
            continue
        try:
            year, month = int(date_str[:4]), int(date_str[5:7])
        except ValueError:
            continue
        key = (year, month)
        buckets[key]["unmatched"].append(
            to_float(row.get("Unmatched callers"))
        )

    return buckets


# ---------------------------------------------------------------------------
# Monthly aggregation — nightly occupancy
# ---------------------------------------------------------------------------

def agg_occupancy(occ_json_path):
    """
    Load daily_occupancy.json and compute monthly nightly totals.

    The file is a flat list of rows; each date has one row per section/key.
    We filter to key=="all_shelter" and use the `ind` field, which equals
    the sum of SERVICE_USER_COUNT across all programs for that night.
    This matches the City's "All Shelter Programs, Total" headcount.

    Returns dict keyed by (year, month) -> list of nightly totals.
    """
    print(f"Loading occupancy data from {occ_json_path} ...", flush=True)
    with open(occ_json_path, encoding="utf-8") as f:
        rows = json.load(f)

    buckets = defaultdict(list)
    for row in rows:
        if row.get("key") != OCC_KEY:
            continue
        date_str = row.get("date", "")
        if not date_str or len(date_str) < 7:
            continue
        try:
            year, month = int(date_str[:4]), int(date_str[5:7])
        except ValueError:
            continue
        ind = row.get("ind")
        if ind is not None:
            buckets[(year, month)].append(float(ind))

    print(f"  Found occupancy data for {len(buckets)} months.", flush=True)
    return buckets


# ---------------------------------------------------------------------------
# Build monthly rows
# ---------------------------------------------------------------------------

def build_monthly(call_buckets, occ_buckets):
    """Combine call/caller and occupancy stats into one row per month."""
    all_keys = sorted(set(call_buckets.keys()) | set(occ_buckets.keys()))
    monthly = []

    for (year, month) in all_keys:
        cb = call_buckets.get((year, month), {})
        ob = occ_buckets.get((year, month), [])

        r_mean, r_sd, r_n, r_se = monthly_agg(cb.get("referred", []))
        h_mean, h_sd, h_n, h_se = monthly_agg(cb.get("handled", []))
        u_mean, u_sd, u_n, u_se = monthly_agg(cb.get("unmatched", []))
        o_mean, o_sd, o_n, o_se = monthly_agg(ob)

        monthly.append({
            "year":  year,
            "month": month,
            "month_label": f"{MONTH_ABBR[month]} {year}",
            # Referred (Code 1A)
            "referred_mean":   r_mean,
            "referred_sd":     r_sd,
            "referred_n_days": r_n,
            "referred_se":     r_se,
            # Handled
            "handled_mean":    h_mean,
            "handled_sd":      h_sd,
            "handled_n_days":  h_n,
            "handled_se":      h_se,
            # Unmatched callers
            "unmatched_mean":  u_mean,
            "unmatched_sd":    u_sd,
            "unmatched_n_days":u_n,
            "unmatched_se":    u_se,
            # Nightly occupancy
            "occupancy_mean":    o_mean,
            "occupancy_sd":      o_sd,
            "occupancy_n_nights":o_n,
            "occupancy_se":      o_se,
        })

    return monthly


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    OUT_DIR.mkdir(exist_ok=True)

    sq_rows  = pull_service_queue()
    wuc_rows = pull_wrap_up_codes()

    print(
        f"Service Queue:   {len(sq_rows):,} rows, "
        f"{sq_rows[0].get('Date')} – {sq_rows[-1].get('Date')}",
        flush=True,
    )
    print(
        f"Wrap-Up Codes:   {len(wuc_rows):,} rows, "
        f"{wuc_rows[0].get('Date')} – {wuc_rows[-1].get('Date')}",
        flush=True,
    )

    call_buckets = agg_call_metrics(sq_rows, wuc_rows)
    occ_buckets  = agg_occupancy(OCC_JSON)

    monthly = build_monthly(call_buckets, occ_buckets)
    print(f"Monthly rows: {len(monthly)}", flush=True)

    output = {
        "service_queue": sq_rows,
        "wrap_up_codes": wuc_rows,
        "monthly":       monthly,
    }

    print(f"Writing {OUT_JSON} ...", flush=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, separators=(",", ":"))
    print(f"  Done. {OUT_JSON.stat().st_size / 1e6:.2f} MB", flush=True)
