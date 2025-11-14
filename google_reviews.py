import requests
import csv
import time
from typing import Dict, List

# --------------- CONFIG ---------------

API_KEY = "AIzaSyBQmiGzRgtUR82WYvf3tb9ei0yrvA4DRok"  # <- REGENERATE & PASTE A FRESH KEY HERE
OUTPUT_FILE = "london_restaurants_grid.csv"

# Target number of unique restaurants
TARGET_PLACES = 1000

# Rough bounding box for Greater London
MIN_LAT = 51.28
MAX_LAT = 51.70
MIN_LNG = -0.51
MAX_LNG = 0.33

# Grid density: more rows/cols = more coverage (and more API calls)
GRID_ROWS = 10
GRID_COLS = 10

# Radius in meters for each Nearby search circle
RADIUS_METERS = 2000.0

NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"

# Nearby Search (New) uses a FieldMask – no spaces allowed
FIELD_MASK = (
    "places.id,"
    "places.displayName,"
    "places.formattedAddress,"
    "places.location,"
    "places.rating,"
    "places.userRatingCount,"
    "places.types,"
    "places.priceLevel,"
    "places.regularOpeningHours.weekdayDescriptions"
)

HEADERS = {
    "Content-Type": "application/json",
    "X-Goog-Api-Key": API_KEY,
    "X-Goog-FieldMask": FIELD_MASK,
}

# --------------- HELPERS ---------------

def nearby_restaurants_at_point(lat: float, lng: float) -> List[Dict]:
    """
    Call Places Nearby Search (v1) at a given point.
    NOTE: Nearby Search (New) does NOT paginate; instead you use maxResultCount.
    """
    body = {
        "includedTypes": ["restaurant"],
        "maxResultCount": 20,  # max results to return for this point
        "locationRestriction": {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": RADIUS_METERS,
            }
        },
    }

    resp = requests.post(NEARBY_URL, headers=HEADERS, json=body)

    if resp.status_code != 200:
        print("Nearby error response:", resp.status_code, resp.text)
        resp.raise_for_status()

    data = resp.json()
    return data.get("places", [])


def normalize_place(place: Dict) -> Dict:
    """
    Flatten a v1 Place object into a CSV-friendly dict.
    """
    display_name = (place.get("displayName") or {}).get("text", "N/A")
    address = place.get("formattedAddress", "N/A")

    location = place.get("location", {}) or {}
    lat = location.get("latitude", "N/A")
    lng = location.get("longitude", "N/A")

    rating = place.get("rating", "N/A")
    num_reviews = place.get("userRatingCount", 0)

    types = place.get("types", []) or []
    food_types = [t for t in types if t not in ["restaurant", "food", "point_of_interest", "establishment"]]
    food_types_str = ", ".join(food_types) if food_types else "N/A"

    price_level = place.get("priceLevel", "N/A")

    opening = place.get("regularOpeningHours") or {}
    weekday_descriptions = opening.get("weekdayDescriptions", []) or []
    hours_text = "; ".join(weekday_descriptions) if weekday_descriptions else "N/A"

    return {
        "name": display_name,
        "address": address,
        "latitude": lat,
        "longitude": lng,
        "rating": rating,
        "num_reviews": num_reviews,
        "food_types": food_types_str,
        "price_level": price_level,
        "hours": hours_text,
        "place_id": place.get("id", "N/A"),
    }


def export_to_csv(restaurants: List[Dict], filename: str):
    if not restaurants:
        print("No data to export.")
        return

    fieldnames = [
        "name",
        "address",
        "latitude",
        "longitude",
        "rating",
        "num_reviews",
        "food_types",
        "price_level",
        "hours",
        "place_id",
    ]

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(restaurants)

    print(f"Exported {len(restaurants)} restaurants to {filename}")


# --------------- MAIN ---------------

def main():
    print("Scanning Greater London in a grid for restaurants...")
    print(f"Target unique restaurants: {TARGET_PLACES}\n")

    # Store places by id to de-duplicate
    places_by_id: Dict[str, Dict] = {}

    lat_step = (MAX_LAT - MIN_LAT) / (GRID_ROWS - 1)
    lng_step = (MAX_LNG - MIN_LNG) / (GRID_COLS - 1)

    for i in range(GRID_ROWS):
        for j in range(GRID_COLS):
            lat = MIN_LAT + i * lat_step
            lng = MIN_LNG + j * lng_step
            print(f"\nGrid cell ({i+1}/{GRID_ROWS}, {j+1}/{GRID_COLS}) at lat={lat:.4f}, lng={lng:.4f}")

            try:
                nearby_places = nearby_restaurants_at_point(lat, lng)
            except Exception as e:
                print(f"Error at {lat}, {lng}: {e}")
                continue

            added_here = 0
            for p in nearby_places:
                pid = p.get("id")
                if pid and pid not in places_by_id:
                    places_by_id[pid] = p
                    added_here += 1

            print(f"  Found {len(nearby_places)} results, {added_here} new (unique) places.")
            print(f"  Total unique so far: {len(places_by_id)}")

            # Gentle throttling between grid points
            time.sleep(0.5)

            if len(places_by_id) >= TARGET_PLACES:
                print("\nReached target number of places, stopping grid scan.")
                break
        if len(places_by_id) >= TARGET_PLACES:
            break

    print(f"\nTotal unique restaurants collected: {len(places_by_id)}")

    restaurants = [normalize_place(p) for p in places_by_id.values()]
    export_to_csv(restaurants, OUTPUT_FILE)

    # Average rating
    numeric_ratings = [r["rating"] for r in restaurants if isinstance(r["rating"], (int, float))]
    if numeric_ratings:
        avg_rating = sum(numeric_ratings) / len(numeric_ratings)
        print(f"Average rating: {avg_rating:.2f}")
    else:
        print("No numeric ratings to compute average.")

    print("\n✓ Done.")


if __name__ == "__main__":
    main()
