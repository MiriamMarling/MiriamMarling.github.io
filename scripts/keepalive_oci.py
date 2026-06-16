"""
OCI Always Free keepalive — a trivial heartbeat connection to the Autonomous DB.

Why this exists: OCI Always Free Autonomous Databases are automatically STOPPED
after 7 consecutive days with no connections (and eventually reclaimed if left
stopped). That database backs the public APEX dashboard, so a stop takes the
dashboard offline. The daily site workflow already connects via
generate_data.py, but if that pull fails for 7 days straight the database would
silently stop. This script is a dedicated, minimal heartbeat (SELECT 1 FROM
DUAL) that runs independently — with continue-on-error in CI — so the keepalive
survives even when the data pull does not. DO NOT REMOVE without an alternative
keepalive in place.

Reads OCI_DSN / OCI_DB_USER / OCI_DB_PASS from the environment (GitHub Actions
secrets), falling back to the sibling ../toronto-shelter-db/.env for local runs
— matching generate_data.py's credential handling.

Author: Miriam Marling <miriam@BonQuery.ca>
Date: 2026
"""

import os
import ssl
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import oracledb
except ModuleNotFoundError:
    print("oracledb not found. Run from the shelter-db venv:")
    print("  ../toronto-shelter-db/venv/bin/python3 scripts/keepalive_oci.py")
    sys.exit(1)


def _toronto_shelter_db_root() -> Path:
    """Sibling toronto-shelter-db repo root (env override, else conventional sibling)."""
    env = os.environ.get("TORONTO_SHELTER_DB")
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "toronto-shelter-db"


# Load .env from the shelter-db sibling repo if OCI_DSN is not already set.
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
    print("Missing OCI_DSN / OCI_DB_USER / OCI_DB_PASS — cannot ping OCI.")
    sys.exit(1)

DSN = "".join(DSN.split())  # OCI Console sometimes inserts whitespace into the DSN


def main() -> int:
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    with oracledb.connect(user=USER, password=PASSWORD, dsn=DSN,
                          ssl_context=ssl_ctx) as conn:
        (result,) = conn.cursor().execute("SELECT 1 FROM DUAL").fetchone()
    print(f"{stamp}  OCI alive (SELECT 1 FROM DUAL -> {result})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
