"""
Pulls all rows from SHELTER.shelter_system_flow in Oracle and exports
as JSON for use by the Quarto dashboard pages. Run before quarto
render/preview when data has changed.

Author: Miriam Marling <miriam@BonQuery.ca>
Date: 2026

Usage:
    # Load credentials from the shelter-db .env file, then run:
    export $(grep -v '^#' ../toronto-shelter-db/.env | xargs)
    python3 scripts/generate_data.py

    # Or, if oracledb is not in your global Python, use the shelter-db venv:
    ../toronto-shelter-db/venv/bin/python3 scripts/generate_data.py
"""

import json
import os
import ssl
import sys
from pathlib import Path

try:
    import oracledb
except ModuleNotFoundError:
    print("oracledb not found. Run from the shelter-db venv:")
    print("  ../toronto-shelter-db/venv/bin/python3 scripts/generate_data.py")
    sys.exit(1)

def _toronto_shelter_db_root() -> Path:
    """Root of the sibling toronto-shelter-db repo.

    Prefer the TORONTO_SHELTER_DB environment variable; otherwise fall back to
    the conventional sibling checkout (../toronto-shelter-db). The fallback
    reproduces the historical relative path, so unconfigured setups keep working.
    """
    env = os.environ.get("TORONTO_SHELTER_DB")
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "toronto-shelter-db"


# Optional: load .env from the shelter-db sibling repo if OCI_DSN is not set.
if not os.environ.get("OCI_DSN"):
    env_file = _toronto_shelter_db_root() / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())

DSN = os.environ.get("OCI_DSN")
USER = os.environ.get("OCI_DB_USER")
PASSWORD = os.environ.get("OCI_DB_PASS")

if not all([DSN, USER, PASSWORD]):
    print("Missing required environment variables: OCI_DSN, OCI_DB_USER, OCI_DB_PASS")
    print("Export them or place them in ../toronto-shelter-db/.env")
    sys.exit(1)

# Remove whitespace from DSN (OCI Console sometimes inserts spaces/newlines).
DSN = "".join(DSN.split())

OUTPUT_PATH = Path(__file__).parent.parent / "data" / "shelter_flow.json"
OUTPUT_PATH.parent.mkdir(exist_ok=True)


def fetch_all_rows():
    """Pull every row from shelter_system_flow as a list of dicts."""
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    with oracledb.connect(user=USER, password=PASSWORD, dsn=DSN,
                          ssl_context=ssl_ctx) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT source_id, TO_CHAR(flow_date, 'YYYY-MM-DD') AS flow_date,
                   population_group, returned_from_housing, returned_to_shelter,
                   newly_identified, moved_to_housing, became_inactive,
                   actively_homeless, age_under_16, age_16_24, age_25_34,
                   age_35_44, age_45_54, age_55_64, age_65_over,
                   gender_male, gender_female, gender_trans_nb_two_spirit,
                   population_group_pct
            FROM shelter_system_flow
            ORDER BY flow_date, population_group
        """)
        columns = [col[0].lower() for col in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

    return rows


if __name__ == "__main__":
    print("Fetching data from OCI...")
    rows = fetch_all_rows()
    print(f"Fetched {len(rows)} rows.")

    with open(OUTPUT_PATH, "w") as f:
        json.dump(rows, f, indent=2)

    size_kb = OUTPUT_PATH.stat().st_size / 1024
    print(f"Wrote: {OUTPUT_PATH}  ({size_kb:.0f} KB)")
