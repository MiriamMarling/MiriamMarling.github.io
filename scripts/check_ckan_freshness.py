#!/usr/bin/env python3
"""
Check whether a Toronto CKAN package has been updated since the last
successful run. Intended for use in GitHub Actions guard jobs.

Usage:
    python check_ckan_freshness.py <package-id> [stored-timestamp]

Exits 0 always (fail-open: a wrong "skip" silently drops data; a wrong
"run" merely no-ops at the existing hash gate). Writes to $GITHUB_OUTPUT:
    should_run=true|false
    metadata_modified=<ISO timestamp from CKAN, or empty on error>

should_run is False only when the current CKAN metadata_modified is
lexicographically <= the stored timestamp (ISO 8601 strings, UTC, no
offset suffix — lexicographic order equals chronological order).
On any error (network, parse, missing sentinel) should_run=true.
"""

import json
import os
import sys
import urllib.request

CKAN_BASE = (
    "https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action"
)


def write_output(key: str, value: str) -> None:
    """Write key=value to $GITHUB_OUTPUT and echo for log visibility."""
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as fh:
            fh.write(f"{key}={value}\n")
    print(f"  {key} = {value}")


def main() -> None:
    if len(sys.argv) < 2:
        print(
            "Usage: check_ckan_freshness.py <package-id> [stored-timestamp]",
            file=sys.stderr,
        )
        write_output("should_run", "true")
        write_output("metadata_modified", "")
        return

    package_id = sys.argv[1]
    stored = sys.argv[2].strip() if len(sys.argv) > 2 else ""

    url = f"{CKAN_BASE}/package_show?id={package_id}"
    print(f"Package  : {package_id}")
    print(f"Stored   : {stored or '(none)'}")

    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "bonquery-ci/1.0"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        if not data.get("success"):
            raise ValueError(
                f"CKAN returned success=false: {data.get('error')}"
            )
        current = data["result"]["metadata_modified"]
    except Exception as exc:  # noqa: BLE001
        print(
            f"WARNING: CKAN check failed ({exc}); defaulting to should_run=true",
            file=sys.stderr,
        )
        write_output("should_run", "true")
        write_output("metadata_modified", "")
        return

    print(f"Current  : {current}")

    if stored and current <= stored:
        print(f"No update since {stored!r}; skipping heavy job.")
        write_output("should_run", "false")
    else:
        reason = "no prior sentinel" if not stored else f"advanced past {stored!r}"
        print(f"Dataset updated ({reason}); running.")
        write_output("should_run", "true")

    write_output("metadata_modified", current)


if __name__ == "__main__":
    main()
