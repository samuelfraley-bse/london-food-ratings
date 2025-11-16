import csv
import time
from typing import Dict, List
import requests

# --------------- CONFIG ---------------

API_KEY = "AIzaSyBQmiGzRgtUR82WYvf3tb9ei0yrvA4DRok"  # <- paste your key here
OUTPUT_FILE = "london_places_summary.csv"

# Target number of unique restaurants/bars/cafes
TARGET_PLACES = 10000  # you'll probably end up in the 5k–10k range

# Rough bounding box for Greater London
MIN_LAT = 51.28
MAX_LAT = 51.70
MIN_LNG = -0.51
MAX_LNG = 0.33

# Grid: denser + smaller radius to reduce overlap and find more uniques
GRID_ROWS = 25
GRID_COLS = 25
RADIUS_METERS = 800.0

NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"

# Only proper food/drink venues – restaurants, bars, cafes, takeaways, etc.
ALLOWED_TYPES = {
    # Generic + style-specific restaurants
    "restaurant",
    "fine_dining_restaurant",
    "fast_food_restaurant",
    "buffet_restaurant",
    "barbecue_restaurant",
    "dessert_restaurant",
    "steak_house",
    "seafood_restaurant",
    "diner",

    # Cuisine-specific restaurants
    "afghani_restaurant",
    "african_restaurant",
    "american_restaurant",
    "asian_restaurant",
    "brazilian_restaurant",
    "french_restaurant",
    "greek_restaurant",
    "indian_restaurant",
    "italian_restaurant",
    "japanese_restaurant",
    "korean_restaurant",
    "lebanese_restaurant",
    "mediterranean_restaurant",
    "mexican_restaurant",
    "middle_eastern_restaurant",
    "pizza_restaurant",
    "spanish_restaurant",
    "sushi_restaurant",
    "thai_restaurant",
    "turkish_restaurant",
    "vegan_restaurant",
    "vegetarian_restaurant",
    "vietnamese_restaurant",

    # Cafés / light food
    "cafe",
    "coffee_shop",
    "tea_house",
    "bagel_shop",
    "bakery",
    "donut_shop",
    "juice_shop",
    "dessert_shop",
    "breakfast_restaurant",
    "brunch_restaurant",

    # Takeaway / delivery
    "meal_takeaway",
    "meal_delivery",
    "food_delivery",
    "food_court",
    "sandwich_shop",
    "deli",

    # Drinking venues that usually serve food
    "pub",
    "bar",
    "bar_and_grill",
    "wine_bar",
}

# Nearby: base info (no reviews)
NEARBY_FIELD_MASK = (
    "places.id,"
    "places.displayName,"
    "places.formattedAddress,"
    "places.location,"
    "places.types,"
    "places.rating,"
    "places.userRatingCount,"
    "places.priceLevel,"
    "places.regularOpeningHours.weekdayDescriptions"
)

HEADERS = {
    "Content-Type": "application/json",
    "X-Goog-Api-Key": API_KEY,
    "X-Goog-FieldMask": NEARBY_FIELD_MASK,
}

# --------------- HELPERS ---------------

def nearby_food_places_at_point(lat: float, lng: float) -> List[Dict]:
    """
    Call Places Nearby Search (v1) at a given point, restricted to restaurant/bar/cafe types.
    """
    body = {
        "includedTypes": [
            "restaurant",
            "bar",
            "pub",
            "cafe",
            "meal_takeaway",
            "meal_delivery",
            "pizza_restaurant",
            "fast_food_restaurant",
            "bar_and_grill",
            "breakfast_restaurant",
            "brunch_restaurant",
            "dessert_restaurant",
        ],
        "maxResultCount": 20,  # API max
        "locationRestriction": {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": RADIUS_METERS,
            }
        },
    }

    resp = requests.post(NEARBY_URL, headers=HEADERS, json=body)

    if resp.status_code != 200:
        print("Nearby error response:", resp.status_code, resp.text[:300])
        resp.raise_for_status()

    data = resp.json()
    return data.get("places", [])


def is_allowed_place(place: Dict) -> bool:
    """
    Check if a place has at least one type in ALLOWED_TYPES.
    """
    types = place.get("types", []) or []
    return any(t in ALLOWED_TYPES for t in types)


def normalize_place(place: Dict) -> Dict:
    """
    Flatten a Nearby result into a CSV-friendly dict (one row per place).
    """
    display_name = (place.get("displayName") or {}).get("text", "N/A")
    address = place.get("formattedAddress", "N/A")

    location = place.get("location", {}) or {}
    lat = location.get("latitude", "N/A")
    lng = location.get("longitude", "N/A")

    rating = place.get("rating", "N/A")
    num_reviews = place.get("userRatingCount", 0)

    types = place.get("types", []) or []
    food_types = [t for t in types if t in ALLOWED_TYPES]
    food_types_str = ", ".join(food_types) if food_types else "N/A"

    price_level = place.get("priceLevel", "N/A")

    opening = place.get("regularOpeningHours") or {}
    weekday_descriptions = opening.get("weekdayDescriptions", []) or []
    hours_text = "; ".join(weekday_descriptions) if weekday_descriptions else "N/A"

    return {
        "place_id": place.get("id", "N/A"),
        "name": display_name,
        "address": address,
        "latitude": lat,
        "longitude": lng,
        "rating": rating,
        "num_reviews": num_reviews,
        "food_types": food_types_str,
        "price_level": price_level,
        "hours": hours_text,
    }


def export_to_csv(rows: List[Dict], filename: str):
    if not rows:
        print("No data to export.")
        return

    fieldnames = [
        "place_id",
        "name",
        "address",
        "latitude",
        "longitude",
        "rating",
        "num_reviews",
        "food_types",
        "price_level",
        "hours",
    ]

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Exported {len(rows)} places to {filename}")


# --------------- MAIN ---------------

def main():
    print("Scanning Greater London grid for restaurants/bars/cafes...")
    print(f"Target unique places: {TARGET_PLACES}\n")

    places_by_id: Dict[str, Dict] = {}

    lat_step = (MAX_LAT - MIN_LAT) / (GRID_ROWS - 1)
    lng_step = (MAX_LNG - MIN_LNG) / (GRID_COLS - 1)

    # GRID SCAN (Nearby only)
    for i in range(GRID_ROWS):
        for j in range(GRID_COLS):
            if len(places_by_id) >= TARGET_PLACES:
                break

            lat = MIN_LAT + i * lat_step
            lng = MIN_LNG + j * lng_step
            print(f"\nGrid cell ({i+1}/{GRID_ROWS}, {j+1}/{GRID_COLS}) at lat={lat:.4f}, lng={lng:.4f}")

            try:
                nearby_places = nearby_food_places_at_point(lat, lng)
            except Exception as e:
                print(f"Error at {lat}, {lng}: {e}")
                continue

            added_here = 0
            for p in nearby_places:
                if not is_allowed_place(p):
                    continue
                pid = p.get("id")
                if pid and pid not in places_by_id:
                    places_by_id[pid] = p
                    added_here += 1

            print(f"  Nearby results: {len(nearby_places)}, new unique food places: {added_here}")
            print(f"  Total unique places so far: {len(places_by_id)}")

            time.sleep(0.4)  # throttle a bit

        if len(places_by_id) >= TARGET_PLACES:
            print("\nReached target number of places, stopping grid scan.")
            break

    print(f"\nTotal unique food places collected from grid: {len(places_by_id)}")

    rows = [normalize_place(p) for p in places_by_id.values()]
    export_to_csv(rows, OUTPUT_FILE)

    print("\n✓ Done.")


if __name__ == "__main__":
    main()
