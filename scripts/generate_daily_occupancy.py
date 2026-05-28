"""
Pulls the City of Toronto Daily Shelter & Overnight Service Occupancy & Capacity
dataset from CKAN, aggregates every date into the City's report row structure,
and writes two files:
  data/daily_occupancy.json          — consumed by OJS on toronto-shelter.qmd
  data/city_reference_2026-05-14.json — reference snapshot for data-validation.qmd

No external dependencies beyond the Python standard library.

Author: Miriam Marling <miriam@BonQuery.ca>
Date: 2026
"""

import csv
import gzip
import io
import json
import re
import ssl
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

# Permissive SSL context — needed on macOS where Python's CA bundle can be
# incomplete. On Linux (GitHub Actions ubuntu-latest) the system CAs work fine
# and this context is harmless.
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

CKAN_BASE  = "https://ckan0.cf.opendata.inter.prod-toronto.ca"
PKG_ID     = "daily-shelter-overnight-service-occupancy-capacity"
OUT_DIR       = Path(__file__).parent.parent / "data"
OUT_JSON      = OUT_DIR / "daily_occupancy.json"
REF_JSON      = OUT_DIR / "city_reference_2026-05-14.json"
SNAPSHOTS_DIR = OUT_DIR / "snapshots"

SCHEMA_VERSION = 1

TEMP_PROG  = "Temporary Programs"
EMERG_TYPES = {"Shelter", "Top Bunk Contingency Space",
               "Alternative Space Protocol", "Surge site"}


# ---------------------------------------------------------------------------
# CKAN helpers
# ---------------------------------------------------------------------------

def ckan_get(endpoint, **params):
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{CKAN_BASE}/api/3/action/{endpoint}?{qs}"
    with urllib.request.urlopen(url, context=_SSL_CTX, timeout=30) as r:
        return json.loads(r.read().decode())["result"]


def download_csv(url):
    print(f"  Downloading {url.split('/')[-1]} ...", flush=True)
    req = urllib.request.Request(url, headers={"Accept-Encoding": "identity"})
    with urllib.request.urlopen(req, context=_SSL_CTX, timeout=180) as r:
        return r.read().decode("utf-8", errors="replace")


def fix_date(s):
    """Normalise YY-MM-DD (2021 resource) to YYYY-MM-DD."""
    if s and re.match(r"^\d{2}-\d{2}-\d{2}$", s):
        return "20" + s
    return s


def to_float(s):
    try:
        return float(s) if s not in (None, "", '""') else 0.0
    except (ValueError, TypeError):
        return 0.0


# ---------------------------------------------------------------------------
# Pull raw data
# ---------------------------------------------------------------------------

def pull_all():
    print("Querying CKAN package_show ...", flush=True)
    resources = ckan_get("package_show", id=PKG_ID)["resources"]
    dump_urls = [r["url"] for r in resources if "datastore/dump" in r.get("url", "")]
    print(f"Found {len(dump_urls)} datastore dump resources.", flush=True)

    all_rows = []
    for url in dump_urls:
        text = download_csv(url)
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            row["OCCUPANCY_DATE"] = fix_date(row.get("OCCUPANCY_DATE", ""))
            all_rows.append(row)

    print(f"Total rows: {len(all_rows):,}", flush=True)
    return all_rows


# ---------------------------------------------------------------------------
# Aggregation (mirrors aggregate_daily_occupancy.R)
# ---------------------------------------------------------------------------

def agg_rooms(rows):
    ind         = sum(to_float(r.get("SERVICE_USER_COUNT", 0))    for r in rows)
    occ         = sum(to_float(r.get("OCCUPIED_ROOMS", 0))        for r in rows)
    cap         = sum(to_float(r.get("CAPACITY_ACTUAL_ROOM", 0))  for r in rows)
    cap_funding = sum(to_float(r.get("CAPACITY_FUNDING_ROOM", 0)) for r in rows)
    unocc = cap - occ
    rate  = round(occ / cap * 100, 1) if cap > 0 else None
    return {"ind": int(ind), "occ": int(occ), "unocc": int(unocc),
            "cap": int(cap), "cap_funding": int(cap_funding), "rate": rate}


def agg_beds(rows):
    ind         = sum(to_float(r.get("SERVICE_USER_COUNT", 0))   for r in rows)
    occ         = sum(to_float(r.get("OCCUPIED_BEDS", 0))        for r in rows)
    cap         = sum(to_float(r.get("CAPACITY_ACTUAL_BED", 0))  for r in rows)
    cap_funding = sum(to_float(r.get("CAPACITY_FUNDING_BED", 0)) for r in rows)
    unocc = cap - occ
    rate  = round(occ / cap * 100, 1) if cap > 0 else None
    return {"ind": int(ind), "occ": int(occ), "unocc": int(unocc),
            "cap": int(cap), "cap_funding": int(cap_funding), "rate": rate}


def rollup(*aggs):
    ind         = sum(a["ind"] for a in aggs)
    occ         = sum(a["occ"] for a in aggs)
    cap         = sum(a["cap"] for a in aggs)
    cap_funding = sum(a.get("cap_funding", 0) or 0 for a in aggs)
    unocc       = cap - occ
    rate        = round(occ / cap * 100, 1) if cap > 0 else None
    return {"ind": ind, "occ": occ, "unocc": unocc,
            "cap": cap, "cap_funding": cap_funding, "rate": rate}


def null_agg(ind):
    return {"ind": ind, "occ": None, "unocc": None,
            "cap": None, "cap_funding": None, "rate": None}


def make_row(key, label, indent, is_total, section, col_type, g, dt):
    return {
        "date":         dt,
        "key":          key,
        "label":        label,
        "indent":       indent,
        "is_total":     is_total,
        "section":      section,
        "col_type":     col_type,
        "ind":          g["ind"],
        "occ":          g["occ"],
        "unocc":        g["unocc"],
        "cap":          g["cap"],
        "cap_funding":  g.get("cap_funding"),
        "rate":         g["rate"],
    }


def aggregate_day(day_rows, dt):
    f = day_rows   # alias

    def flt(**kw):
        result = f
        for k, v in kw.items():
            if isinstance(v, set):
                result = [r for r in result if r.get(k) in v]
            elif isinstance(v, str) and v.startswith("!"):
                result = [r for r in result if r.get(k) != v[1:]]
            else:
                result = [r for r in result if r.get(k) == v]
        return result

    g_fam_emerg    = agg_rooms(flt(SECTOR="Families", PROGRAM_MODEL="Emergency",
                                   OVERNIGHT_SERVICE_TYPE="Shelter",
                                   CAPACITY_TYPE="Room Based Capacity"))
    g_fam_trans_r  = agg_rooms(flt(SECTOR="Families", PROGRAM_MODEL="Transitional",
                                   OVERNIGHT_SERVICE_TYPE="Shelter",
                                   CAPACITY_TYPE="Room Based Capacity"))
    g_fam_hotel    = agg_rooms([r for r in f
                                if r.get("SECTOR") == "Families"
                                and r.get("OVERNIGHT_SERVICE_TYPE") == "Motel/Hotel Shelter"
                                and r.get("PROGRAM_AREA") != TEMP_PROG])

    sng_hotel_all  = [r for r in f
                      if r.get("SECTOR") != "Families"
                      and r.get("OVERNIGHT_SERVICE_TYPE") == "Motel/Hotel Shelter"
                      and r.get("PROGRAM_AREA") != TEMP_PROG]
    sng_rooms      = agg_rooms([r for r in sng_hotel_all if r.get("CAPACITY_TYPE") == "Room Based Capacity"])
    sng_beds       = agg_beds( [r for r in sng_hotel_all if r.get("CAPACITY_TYPE") == "Bed Based Capacity"])
    g_sng_hotel    = {"ind": sng_beds["ind"] + sng_rooms["ind"],
                      "occ": sng_rooms["occ"], "unocc": sng_rooms["unocc"],
                      "cap": sng_rooms["cap"], "cap_funding": sng_rooms["cap_funding"],
                      "rate": sng_rooms["rate"]}

    g_mix_emerg = agg_beds([r for r in f
                            if r.get("SECTOR") == "Mixed Adult"
                            and r.get("PROGRAM_MODEL") == "Emergency"
                            and r.get("OVERNIGHT_SERVICE_TYPE") in EMERG_TYPES
                            and r.get("CAPACITY_TYPE") == "Bed Based Capacity"])
    g_men_emerg = agg_beds(flt(SECTOR="Men",   PROGRAM_MODEL="Emergency",
                               OVERNIGHT_SERVICE_TYPE=EMERG_TYPES,
                               CAPACITY_TYPE="Bed Based Capacity"))
    g_wom_emerg = agg_beds(flt(SECTOR="Women", PROGRAM_MODEL="Emergency",
                               OVERNIGHT_SERVICE_TYPE=EMERG_TYPES,
                               CAPACITY_TYPE="Bed Based Capacity"))
    g_yth_emerg = agg_beds(flt(SECTOR="Youth", PROGRAM_MODEL="Emergency",
                               OVERNIGHT_SERVICE_TYPE=EMERG_TYPES,
                               CAPACITY_TYPE="Bed Based Capacity"))

    g_mix_trans  = agg_beds(flt(SECTOR="Mixed Adult", PROGRAM_MODEL="Transitional",
                                CAPACITY_TYPE="Bed Based Capacity"))
    g_fam_trans_b= agg_beds(flt(SECTOR="Families",   PROGRAM_MODEL="Transitional",
                                CAPACITY_TYPE="Bed Based Capacity"))
    g_men_trans  = agg_beds(flt(SECTOR="Men",         PROGRAM_MODEL="Transitional",
                                CAPACITY_TYPE="Bed Based Capacity"))
    g_wom_trans  = agg_beds(flt(SECTOR="Women",       PROGRAM_MODEL="Transitional",
                                CAPACITY_TYPE="Bed Based Capacity"))
    g_yth_trans  = agg_beds(flt(SECTOR="Youth",       PROGRAM_MODEL="Transitional",
                                CAPACITY_TYPE="Bed Based Capacity"))

    g_respites   = agg_beds([r for r in f
                             if r.get("OVERNIGHT_SERVICE_TYPE") == "24-Hour Respite Site"
                             and r.get("PROGRAM_AREA") != TEMP_PROG])
    g_dropin     = agg_beds(flt(OVERNIGHT_SERVICE_TYPE="24-Hour Women's Drop-in"))
    g_temp_resp  = agg_beds([r for r in f
                             if r.get("OVERNIGHT_SERVICE_TYPE") == "24-Hour Respite Site"
                             and r.get("PROGRAM_AREA") == TEMP_PROG])
    g_hotels     = agg_rooms([r for r in f
                              if r.get("OVERNIGHT_SERVICE_TYPE") == "Motel/Hotel Shelter"
                              and r.get("PROGRAM_AREA") == TEMP_PROG])
    g_iso        = agg_rooms(flt(OVERNIGHT_SERVICE_TYPE="Isolation/Recovery Site"))

    g_fam_total     = rollup(g_fam_emerg, g_fam_trans_r, g_fam_hotel)
    g_emerg_total   = rollup(g_mix_emerg, g_men_emerg, g_wom_emerg, g_yth_emerg)
    g_trans_total   = rollup(g_mix_trans, g_fam_trans_b, g_men_trans, g_wom_trans, g_yth_trans)
    g_singles_total = rollup(g_emerg_total, g_trans_total)
    g_allied_total  = rollup(g_respites, g_dropin)
    g_temp_total    = null_agg(g_temp_resp["ind"] + g_hotels["ind"])
    g_shelter_total = null_agg(
        g_fam_total["ind"] + g_sng_hotel["ind"] + g_singles_total["ind"] +
        g_allied_total["ind"] + g_temp_total["ind"] + g_iso["ind"]
    )
    g_room_total    = null_agg(g_fam_total["ind"] + g_sng_hotel["ind"])

    R = make_row
    S = "summary"; RB = "room_based"; BB = "bed_based"; AL = "allied"
    TB = "temp_bed"; TR = "temp_room"; IR = "iso_recovery"
    SUM = "summary"; ROM = "room"; BED = "bed"

    singles_sector_ind = g_singles_total["ind"] + g_allied_total["ind"] + g_temp_total["ind"]

    return [
        R("all_shelter",    "All Shelter Programs, Total",         0, True,  S,  SUM, g_shelter_total, dt),
        R("room_based",     "Shelter Programs, Room-Based, Total", 1, True,  S,  SUM, g_room_total,    dt),
        R("singles_sector", "Singles Sector Programs, Total",      1, True,  S,  SUM, null_agg(singles_sector_ind), dt),
        R("singles_shelter","  Shelter Programs, Singles, Total",  2, False, S,  SUM, g_singles_total, dt),
        R("allied_summ",    "  Allied Services, Total",            2, False, S,  SUM, g_allied_total,  dt),
        R("temp_summ",      "  Temporary Programs, Total",         2, False, S,  SUM, g_temp_total,    dt),
        R("iso_summ",       "Temporary Isolation/Recovery Programs",1,False, S,  SUM, g_iso,           dt),
        R("fam_total",      "Family Sector, Total",                0, True,  RB, ROM, g_fam_total,     dt),
        R("fam_emerg",      "Families, Emergency Shelter Programs",1, False, RB, ROM, g_fam_emerg,     dt),
        R("fam_trans_r",    "Families, Transitional Shelter Programs",1,False,RB,ROM, g_fam_trans_r,   dt),
        R("fam_hotel",      "Families, Motel/Hotel Programs",      1, False, RB, ROM, g_fam_hotel,     dt),
        R("sng_hotel",      "Single Sector Motel/Hotel, Total",    0, True,  RB, ROM, g_sng_hotel,     dt),
        R("singles_total",  "Singles Sectors, Total",              0, True,  BB, BED, g_singles_total, dt),
        R("emerg_total",    "Emergency Shelter Programs, Total",   1, True,  BB, BED, g_emerg_total,   dt),
        R("mix_emerg",      "Mixed Adult, Emergency",              2, False, BB, BED, g_mix_emerg,     dt),
        R("men_emerg",      "Men, Emergency",                      2, False, BB, BED, g_men_emerg,     dt),
        R("wom_emerg",      "Women, Emergency",                    2, False, BB, BED, g_wom_emerg,     dt),
        R("yth_emerg",      "Youth, Emergency",                    2, False, BB, BED, g_yth_emerg,     dt),
        R("trans_total",    "Transitional Shelter Programs, Total",1, True,  BB, BED, g_trans_total,   dt),
        R("mix_trans",      "Mixed Adult, Transitional",           2, False, BB, BED, g_mix_trans,     dt),
        R("fam_trans_b",    "Families, Transitional",              2, False, BB, BED, g_fam_trans_b,   dt),
        R("men_trans",      "Men, Transitional",                   2, False, BB, BED, g_men_trans,     dt),
        R("wom_trans",      "Women, Transitional",                 2, False, BB, BED, g_wom_trans,     dt),
        R("yth_trans",      "Youth, Transitional",                 2, False, BB, BED, g_yth_trans,     dt),
        R("allied_total",   "Allied Services, Total",              0, True,  AL, BED, g_allied_total,  dt),
        R("respites",       "24-Hour Respites",                    1, False, AL, BED, g_respites,      dt),
        R("dropin",         "24-Hour Women's Drop-ins",            1, False, AL, BED, g_dropin,        dt),
        R("temp_resp",      "24-Hour Temporary Response Sites",    0, False, TB, BED, g_temp_resp,     dt),
        R("hotels",         "Hotels",                              0, False, TR, ROM, g_hotels,        dt),
        R("iso",            "Isolation/Recovery Programs Combined Total",0,False,IR,ROM,g_iso,         dt),
    ]


# ---------------------------------------------------------------------------
# City reference snapshot (May 14, 2026 — captured from live dashboard)
# ---------------------------------------------------------------------------

CITY_REF = [
    {"key":"all_shelter",    "label":"All Shelter Programs, Total",                "section":"summary",      "col_type":"summary","city_ind":7971, "city_occ":None,"city_unocc":None,"city_cap":None, "city_rate":None},
    {"key":"room_based",     "label":"Shelter Programs, Room-Based, Total",        "section":"summary",      "col_type":"summary","city_ind":2244, "city_occ":None,"city_unocc":None,"city_cap":None, "city_rate":None},
    {"key":"fam_total",      "label":"Family Sector, Total",                       "section":"room_based",   "col_type":"room",   "city_ind":1740, "city_occ":543, "city_unocc":8,  "city_cap":551,  "city_rate":98.5},
    {"key":"fam_emerg",      "label":"Families, Emergency Shelter Programs",       "section":"room_based",   "col_type":"room",   "city_ind":598,  "city_occ":194, "city_unocc":3,  "city_cap":197,  "city_rate":98.5},
    {"key":"fam_trans_r",    "label":"Families, Transitional Shelter Programs",    "section":"room_based",   "col_type":"room",   "city_ind":322,  "city_occ":115, "city_unocc":3,  "city_cap":118,  "city_rate":97.5},
    {"key":"fam_hotel",      "label":"Families, Motel/Hotel Programs",             "section":"room_based",   "col_type":"room",   "city_ind":820,  "city_occ":234, "city_unocc":2,  "city_cap":236,  "city_rate":99.2},
    {"key":"sng_hotel",      "label":"Single Sector Motel/Hotel, Total",           "section":"room_based",   "col_type":"room",   "city_ind":504,  "city_occ":237, "city_unocc":1,  "city_cap":238,  "city_rate":99.6},
    {"key":"singles_total",  "label":"Singles Sectors, Total",                     "section":"bed_based",    "col_type":"bed",    "city_ind":3477, "city_occ":3477,"city_unocc":165,"city_cap":3642, "city_rate":95.5},
    {"key":"emerg_total",    "label":"Emergency Shelter Programs, Total",          "section":"bed_based",    "col_type":"bed",    "city_ind":2702, "city_occ":2702,"city_unocc":108,"city_cap":2810, "city_rate":96.2},
    {"key":"mix_emerg",      "label":"Mixed Adult, Emergency",                     "section":"bed_based",    "col_type":"bed",    "city_ind":577,  "city_occ":577, "city_unocc":14, "city_cap":591,  "city_rate":97.6},
    {"key":"men_emerg",      "label":"Men, Emergency",                             "section":"bed_based",    "col_type":"bed",    "city_ind":1170, "city_occ":1170,"city_unocc":77, "city_cap":1247, "city_rate":93.8},
    {"key":"wom_emerg",      "label":"Women, Emergency",                           "section":"bed_based",    "col_type":"bed",    "city_ind":512,  "city_occ":512, "city_unocc":11, "city_cap":523,  "city_rate":97.9},
    {"key":"yth_emerg",      "label":"Youth, Emergency",                           "section":"bed_based",    "col_type":"bed",    "city_ind":443,  "city_occ":443, "city_unocc":6,  "city_cap":449,  "city_rate":98.7},
    {"key":"trans_total",    "label":"Transitional Shelter Programs, Total",       "section":"bed_based",    "col_type":"bed",    "city_ind":775,  "city_occ":775, "city_unocc":57, "city_cap":832,  "city_rate":93.1},
    {"key":"mix_trans",      "label":"Mixed Adult, Transitional",                  "section":"bed_based",    "col_type":"bed",    "city_ind":199,  "city_occ":199, "city_unocc":18, "city_cap":217,  "city_rate":91.7},
    {"key":"fam_trans_b",    "label":"Families, Transitional",                     "section":"bed_based",    "col_type":"bed",    "city_ind":16,   "city_occ":16,  "city_unocc":5,  "city_cap":21,   "city_rate":76.2},
    {"key":"men_trans",      "label":"Men, Transitional",                          "section":"bed_based",    "col_type":"bed",    "city_ind":164,  "city_occ":164, "city_unocc":17, "city_cap":181,  "city_rate":90.6},
    {"key":"wom_trans",      "label":"Women, Transitional",                        "section":"bed_based",    "col_type":"bed",    "city_ind":121,  "city_occ":121, "city_unocc":3,  "city_cap":124,  "city_rate":97.6},
    {"key":"yth_trans",      "label":"Youth, Transitional",                        "section":"bed_based",    "col_type":"bed",    "city_ind":275,  "city_occ":275, "city_unocc":14, "city_cap":289,  "city_rate":95.2},
    {"key":"allied_total",   "label":"Allied Services, Total",                     "section":"allied",       "col_type":"bed",    "city_ind":349,  "city_occ":349, "city_unocc":8,  "city_cap":357,  "city_rate":97.8},
    {"key":"respites",       "label":"24-Hour Respites",                           "section":"allied",       "col_type":"bed",    "city_ind":295,  "city_occ":295, "city_unocc":8,  "city_cap":303,  "city_rate":97.4},
    {"key":"dropin",         "label":"24-Hour Women's Drop-ins",                   "section":"allied",       "col_type":"bed",    "city_ind":54,   "city_occ":54,  "city_unocc":0,  "city_cap":54,   "city_rate":100.0},
    {"key":"temp_resp",      "label":"24-Hour Temporary Response Sites",           "section":"temp_bed",     "col_type":"bed",    "city_ind":50,   "city_occ":50,  "city_unocc":0,  "city_cap":50,   "city_rate":100.0},
    {"key":"hotels",         "label":"Hotels",                                     "section":"temp_room",    "col_type":"room",   "city_ind":1851, "city_occ":1422,"city_unocc":4,  "city_cap":1426, "city_rate":99.7},
    {"key":"iso",            "label":"Isolation/Recovery Programs Combined Total", "section":"iso_recovery", "col_type":"room",   "city_ind":0,    "city_occ":0,   "city_unocc":0,  "city_cap":0,    "city_rate":0.0},
]


# ---------------------------------------------------------------------------
# Raw snapshot archival
# ---------------------------------------------------------------------------

def write_snapshot(raw_rows, pulled_at=None):
    """Archive the raw CKAN rows (pre-aggregation) as gzipped JSON.

    Used by the data-drift investigation to diff successive pulls and identify
    which programs (PROGRAM_ID + OCCUPANCY_DATE) were added, removed, or had
    their values revised between releases.
    """
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    pulled_at = pulled_at or datetime.now(timezone.utc)
    stamp = pulled_at.strftime("%Y-%m-%dT%H%M%SZ")
    path = SNAPSHOTS_DIR / f"raw_{stamp}.json.gz"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "pulled_at":      pulled_at.isoformat().replace("+00:00", "Z"),
        "source":         "ckan-datastore-dump",
        "package_id":     PKG_ID,
        "row_count":      len(raw_rows),
        "rows":           raw_rows,
    }
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"))
    print(f"Snapshot: {path} ({path.stat().st_size / 1e6:.1f} MB, {len(raw_rows):,} rows)")
    return path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    OUT_DIR.mkdir(exist_ok=True)

    raw = pull_all()
    write_snapshot(raw)

    # Group rows by date
    by_date = defaultdict(list)
    for row in raw:
        dt = row.get("OCCUPANCY_DATE", "")
        if dt:
            by_date[dt].append(row)

    all_dates = sorted(by_date.keys(), reverse=True)
    print(f"Aggregating {len(all_dates)} dates ...", flush=True)

    result = []
    for i, dt in enumerate(all_dates, 1):
        if i % 200 == 0:
            print(f"  {i}/{len(all_dates)} ...", flush=True)
        result.extend(aggregate_day(by_date[dt], dt))

    print(f"Writing {len(result):,} rows to {OUT_JSON} ...", flush=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, separators=(",", ":"))
    print(f"  {OUT_JSON.stat().st_size / 1e6:.1f} MB")

    with open(REF_JSON, "w", encoding="utf-8") as f:
        json.dump(CITY_REF, f, indent=2)
    print(f"Written: {REF_JSON}")
