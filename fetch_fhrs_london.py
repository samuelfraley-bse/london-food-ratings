import requests
import csv
import time
from typing import Dict, List

# --------------- CONFIG ---------------

OUTPUT_FILE = "fhrs_london.csv"

# Same-ish bounding box as your Google script
MIN_LAT = 51.28
MAX_LAT = 51.70
MIN_LNG = -0.51
MAX_LNG = 0.33

GRID_ROWS = 10
GRID_COLS = 10

# FHRS uses miles for maxDistanceLimit
RADIUS_MILES = 1.3  # ~2.1km

FHRS_URL = "https://api.ratings.food.gov.uk/Establishments"

HEADERS = {
    "x-api-version": "2",
    "accept": "application/json",
}

# --------------- HELPERS ---------------

def fetch_fhrs_at_point(lat: float, lng: float, radius_miles: float = RADIUS_MILES) -> List[Dict]:
    """
    Call FHRS Establishments endpoint around (lat, lng).
    Paginates over pageNumber until no more results.
    """
    page_number = 1
    all_establishments: List[Dict] = []

    while True:
        params = {
            "latitude": lat,
            "longitude": lng,
            "maxDistanceLimit": radius_miles,
            "countryId": 1,           # 1 = England
            "schemeTypeKey": "FHRS",  # hygiene ratings (not Scottish FHIS)
            "pageNumber": page_number,
            "pageSize": 500,          # will be capped by API if too large
            "sortOptionKey": "distance",
        }

        resp = requests.get(FHRS_URL, headers=HEADERS, params=params)
        if resp.status_code != 200:
            print(f"FHRS error {resp.status_code} at {lat}, {lng}: {resp.text[:200]}")
            break

        data = resp.json()
        establishments = data.get("establishments", [])
        if not establishments:
            break

        all_establishments.extend(establishments)

        # If we got fewer than requested, no more pages
        if len(establishments) < params["pageSize"]:
            break

        page_number += 1
        # gentle throttle
        time.sleep(0.2)

    return all_establishments


def normalize_establishment(e: Dict) -> Dict:
    """
    Flatten FHRS establishment into a CSV-friendly dict.
    JSON shape follows FHRS v2 docs.
    """
    geocode = e.get("geocode") or {}
    scores = e.get("scores") or {}

    lat = geocode.get("latitude")
    lng = geocode.get("longitude")

    # Some entries may not be geocoded – skip those later when matching
    return {
        "fhrs_id": e.get("FHRSID"),
        "business_name": e.get("BusinessName"),
        "business_type": e.get("BusinessType"),
        "business_type_id": e.get("BusinessTypeID"),
        "address1": e.get("AddressLine1"),
        "address2": e.get("AddressLine2"),
        "address3": e.get("AddressLine3"),
        "address4": e.get("AddressLine4"),
        "postcode": e.get("PostCode"),
        "rating_value": e.get("RatingValue"),
        "rating_key": e.get("RatingKey"),
        "rating_date": e.get("RatingDate"),
        "local_authority_name": e.get("LocalAuthorityName"),
        "local_authority_code": e.get("LocalAuthorityCode"),
        "local_authority_website": e.get("LocalAuthorityWebSite"),
        "local_authority_email": e.get("LocalAuthorityEmailAddress"),
        "hygiene_score": scores.get("Hygiene"),
        "structural_score": scores.get("Structural"),
        "confidence_in_management_score": scores.get("ConfidenceInManagement"),
        "scheme_type": e.get("SchemeType"),
        "new_rating_pending": e.get("NewRatingPending"),
        "latitude": lat,
        "longitude": lng,
    }


def export_fhrs_to_csv(establishments: List[Dict], filename: str):
    if not establishments:
        print("No FHRS data to export.")
        return

    fieldnames = [
        "fhrs_id",
        "business_name",
        "business_type",
        "business_type_id",
        "address1",
        "address2",
        "address3",
        "address4",
        "postcode",
        "rating_value",
        "rating_key",
        "rating_date",
        "local_authority_name",
        "local_authority_code",
        "local_authority_website",
        "local_authority_email",
        "hygiene_score",
        "structural_score",
        "confidence_in_management_score",
        "scheme_type",
        "new_rating_pending",
        "latitude",
        "longitude",
    ]

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(establishments)

    print(f"Exported {len(establishments)} FHRS establishments to {filename}")


# --------------- MAIN ---------------

def main():
    print("Scanning FHRS around Greater London...")
    fhrs_by_id: Dict[int, Dict] = {}

    lat_step = (MAX_LAT - MIN_LAT) / (GRID_ROWS - 1)
    lng_step = (MAX_LNG - MIN_LNG) / (GRID_COLS - 1)

    for i in range(GRID_ROWS):
        for j in range(GRID_COLS):
            lat = MIN_LAT + i * lat_step
            lng = MIN_LNG + j * lng_step
            print(f"\nGrid cell ({i+1}/{GRID_ROWS}, {j+1}/{GRID_COLS}) at lat={lat:.4f}, lng={lng:.4f}")

            establishments = fetch_fhrs_at_point(lat, lng)

            added_here = 0
            for e in establishments:
                fhrs_id = e.get("FHRSID")
                if fhrs_id and fhrs_id not in fhrs_by_id:
                    fhrs_by_id[fhrs_id] = e
                    added_here += 1

            print(f"  Found {len(establishments)} results, {added_here} new (unique).")
            print(f"  Total unique FHRS so far: {len(fhrs_by_id)}")

            time.sleep(0.4)  # gentle throttle

    normalized = [normalize_establishment(e) for e in fhrs_by_id.values()]
    export_fhrs_to_csv(normalized, OUTPUT_FILE)
    print("\n✓ Done fetching FHRS data.")


if __name__ == "__main__":
    main()
