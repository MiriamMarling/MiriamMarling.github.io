import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

CITY_URL = "https://www.toronto.ca/city-government/data-research-maps/research-reports/housing-and-homelessness-research-and-reports/shelter-census/"

DATA_DIR = Path(__file__).parent.parent / "data"
OCCUPANCY_FILE = DATA_DIR / "daily_occupancy.json"
OUTPUT_FILE = DATA_DIR / "city_validation.json"

# Maps exact City table label text → BonQuery key.
# Only rows where the City label is stable and maps cleanly to a BonQuery key.
LABEL_TO_KEY = {
    "All Shelter Programs, Total":            "all_shelter",
    "Shelter Programs, Room-Based, Total":    "room_based",
    "Singles Sector Programs, Total":         "singles_sector",
    "Family Sector, Total":                   "fam_total",
    "Families, Emergency Shelter Programs":   "fam_emerg",
    "Families, Transitional Shelter Programs":"fam_trans_r",
    "Families, Motel/Hotel Programs":         "fam_hotel",
    "Single Sector Motel/Hotel, Total":       "sng_hotel",
    "Singles Sectors, Total":                 "singles_total",
    "Emergency Shelter Programs, Total":      "emerg_total",
    "Mixed Adult, Emergency":                 "mix_emerg",
    "Men, Emergency":                         "men_emerg",
    "Women, Emergency":                       "wom_emerg",
    "Youth, Emergency":                       "yth_emerg",
    "Transitional Shelter Programs, Total":   "trans_total",
    "Mixed Adult, Transitional":              "mix_trans",
    "Families, Transitional":                 "fam_trans_b",
    "Men, Transitional":                      "men_trans",
    "Women, Transitional":                    "wom_trans",
    "Youth, Transitional":                    "yth_trans",
    "Allied Services, Total":                 "allied_total",
    "24-Hour Respites":                       "respites",
    "24-Hour Women's Drop-ins":               "dropin",
    "24-Hour Temporary Response Sites":       "temp_resp",
    "Hotels":                                 "hotels",
    "Isolation/Recovery Programs Combined Total": "iso",
}

MONTH_NAMES = {
    "January": 1, "February": 2, "March": 3, "April": 4,
    "May": 5, "June": 6, "July": 7, "August": 8,
    "September": 9, "October": 10, "November": 11, "December": 12,
}


def write_result(passed, city_date, mismatches):
    result = {
        "city_date": city_date,
        "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "passed": passed,
        "mismatches": mismatches,
    }
    OUTPUT_FILE.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


def parse_number(text):
    cleaned = re.sub(r"[,\s]", "", text.strip())
    try:
        return int(cleaned)
    except ValueError:
        return None


def extract_city_date(soup):
    for tag in soup.find_all(["h2", "h3", "h4"]):
        text = tag.get_text(strip=True)
        m = re.search(r"Daily Occupancy\s*&\s*Capacity for\s+(\w+)\s+(\d+)", text)
        if m:
            month_str, day_str = m.group(1), m.group(2)
            month = MONTH_NAMES.get(month_str)
            if month:
                year = datetime.now(timezone.utc).year
                return f"{year}-{month:02d}-{int(day_str):02d}"
    return None


def extract_city_values(soup):
    city_values = {}
    for td in soup.find_all("td"):
        label = td.get_text(strip=True)
        if label in LABEL_TO_KEY:
            key = LABEL_TO_KEY[label]
            # The individuals value is the first numeric sibling td in the same row
            row = td.find_parent("tr")
            if not row:
                continue
            cells = row.find_all("td")
            if len(cells) >= 2:
                val = parse_number(cells[1].get_text(strip=True))
                if val is not None and key not in city_values:
                    city_values[key] = val
    return city_values


def main():
    try:
        resp = requests.get(CITY_URL, timeout=30, headers={"User-Agent": "BonQuery-Validator/1.0"})
        resp.raise_for_status()
    except Exception as exc:
        write_result(False, None, [{"label": "City page fetch failed", "key": None, "city": None, "bonquery": str(exc)}])
        sys.exit(0)

    soup = BeautifulSoup(resp.text, "html.parser")

    city_date = extract_city_date(soup)
    if not city_date:
        write_result(False, None, [{"label": "City page date not found", "key": None, "city": None, "bonquery": "Could not parse date heading"}])
        sys.exit(0)

    city_values = extract_city_values(soup)
    if not city_values:
        write_result(False, city_date, [{"label": "City table parse failed", "key": None, "city": None, "bonquery": "No table rows matched expected labels"}])
        sys.exit(0)

    daily_occ = json.loads(OCCUPANCY_FILE.read_text())
    bonquery_rows = {r["key"]: r for r in daily_occ if r["date"] == city_date}

    if not bonquery_rows:
        write_result(False, city_date, [{"label": "No BonQuery data for City date", "key": None, "city": None, "bonquery": f"No rows found for {city_date}"}])
        sys.exit(0)

    mismatches = []
    for label, key in LABEL_TO_KEY.items():
        city_val = city_values.get(key)
        bq_row = bonquery_rows.get(key)
        if city_val is None or bq_row is None:
            continue
        bq_val = bq_row.get("ind")
        if bq_val is None:
            continue
        if city_val != bq_val:
            mismatches.append({"label": label, "key": key, "city": city_val, "bonquery": bq_val})

    write_result(len(mismatches) == 0, city_date, mismatches)


if __name__ == "__main__":
    main()
