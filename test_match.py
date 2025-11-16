import csv
from math import radians, sin, cos, asin, sqrt
from typing import Dict, List, Optional, Tuple

from rapidfuzz import fuzz

# ---------------- CONFIG ----------------

FHRS_CSV = r"C:\Users\sffra\Downloads\BSE 2025-2026\london-food-ratings\fhrs_london.csv"
PLACES_CSV = r"C:\Users\sffra\Downloads\BSE 2025-2026\london-food-ratings\london_restaurants_grid_v2.csv"
OUTPUT_CSV = r"C:\Users\sffra\Downloads\BSE 2025-2026\london-food-ratings\london_match.csv"

# Only consider Google candidates within this many meters of FHRS lat/lng
MAX_DISTANCE_METERS = 500.0  # you can bump to 800 if needed

# Only accept matches whose combined score is at least this
MIN_MATCH_SCORE = 0.5

# Rough bounding box filter for speed (deg of lat/lng ~ km, ish)
LAT_DEG_WINDOW = 0.01   # ~1.1 km
LNG_DEG_WINDOW = 0.015  # ~1 km-ish around London


# ---------------- GEO HELPERS ----------------

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance in meters between two lat/lng points."""
    R = 6371000
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = (sin(dlat / 2) ** 2 +
         cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2)
    c = 2 * asin(sqrt(a))
    return R * c


# ---------------- NORMALISATION HELPERS ----------------

def norm_str(s: str) -> str:
    return " ".join(s.lower().strip().split()) if s else ""


def norm_postcode(pc: str) -> str:
    return (pc or "").replace(" ", "").upper()


# ---------------- DATA LOAD ----------------

def load_places(path: str) -> List[Dict]:
    """
    Load Google places CSV from the grid script.
    Expected columns:
      place_id, name, address, latitude, longitude, rating, num_reviews, food_types, price_level, hours
    """
    places = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                row["latitude"] = float(row.get("latitude") or "nan")
                row["longitude"] = float(row.get("longitude") or "nan")
            except ValueError:
                row["latitude"] = float("nan")
                row["longitude"] = float("nan")
            row["name_norm"] = norm_str(row.get("name", ""))
            row["address_norm"] = norm_str(row.get("address", ""))
            places.append(row)
    return places


def load_fhrs(path: str) -> List[Dict]:
    """
    Load FHRS CSV.
    Expected columns (at least):
      fhrs_id, business_name, postcode, latitude, longitude, rating_value, ...
    """
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row["business_name_norm"] = norm_str(row.get("business_name", ""))
            row["postcode_norm"] = norm_postcode(row.get("postcode", ""))

            try:
                row["lat"] = float(row.get("latitude") or "nan")
                row["lng"] = float(row.get("longitude") or "nan")
            except ValueError:
                row["lat"] = float("nan")
                row["lng"] = float("nan")

            rows.append(row)
    return rows


# ---------------- MATCHING LOGIC ----------------

def distance_component(distance_m: Optional[float]) -> float:
    """
    Turn distance into a score in [0,1], where closer is better.
    If distance is None, return 0.
    """
    if distance_m is None:
        return 0.0
    if distance_m <= 50:
        return 1.0
    if distance_m <= 150:
        return 0.7
    if distance_m <= 300:
        return 0.4
    if distance_m <= MAX_DISTANCE_METERS:
        return 0.2
    return 0.0


def postcode_signal(fhrs_pc_norm: str, google_address_norm: str) -> float:
    """
    Simple postcode signal:
      - 1.0 if FHRS postcode (no space) appears in the Google address (ignoring spaces)
      - 0.0 otherwise
    """
    if not fhrs_pc_norm or not google_address_norm:
        return 0.0
    addr_pc_like = google_address_norm.replace(" ", "").upper()
    return 1.0 if fhrs_pc_norm in addr_pc_like else 0.0


def compute_match_score(fhrs_row: Dict, place: Dict) -> Tuple[float, float, Optional[float]]:
    """
    Compute:
      - combined score in [0,1+]
      - raw name similarity (0–100)
      - distance in meters (or None)
    """
    # Name similarity (0–100)
    name_fhrs = fhrs_row["business_name_norm"]
    name_google = place["name_norm"]
    name_sim = fuzz.token_sort_ratio(name_fhrs, name_google)  # 0–100
    name_score = name_sim / 100.0

    # Distance
    lat_h = fhrs_row["lat"]
    lng_h = fhrs_row["lng"]
    lat_g = place["latitude"]
    lng_g = place["longitude"]

    distance_m = None
    if not any(map(lambda x: x != x, [lat_h, lng_h, lat_g, lng_g])):  # NaN check
        distance_m = haversine(lat_h, lng_h, lat_g, lng_g)

    dist_score = distance_component(distance_m)

    # Postcode signal
    pc_score = postcode_signal(fhrs_row["postcode_norm"], place["address_norm"])

    # Combined score (tune weights if you like)
    combined = (
        0.7 * name_score +
        0.2 * dist_score +
        0.1 * pc_score
    )

    return combined, float(name_sim), distance_m


def find_candidate_places(fhrs_row: Dict, places: List[Dict]) -> List[Dict]:
    """
    Quickly narrow down candidates by approximate lat/lng window.
    """
    lat_h = fhrs_row["lat"]
    lng_h = fhrs_row["lng"]

    # If we don't have coordinates, fall back to all (slow but rare)
    if lat_h != lat_h or lng_h != lng_h:  # NaN check
        return places

    lat_min = lat_h - LAT_DEG_WINDOW
    lat_max = lat_h + LAT_DEG_WINDOW
    lng_min = lng_h - LNG_DEG_WINDOW
    lng_max = lng_h + LNG_DEG_WINDOW

    candidates = []
    for p in places:
        lat_g = p["latitude"]
        lng_g = p["longitude"]
        if lat_g != lat_g or lng_g != lng_g:
            continue
        if (lat_min <= lat_g <= lat_max) and (lng_min <= lng_g <= lng_max):
            candidates.append(p)

    return candidates


def match_one_fhrs(fhrs_row: Dict, places: List[Dict]) -> Tuple[Optional[Dict], float, float, Optional[float]]:
    """
    For a single FHRS row, find best Google place.
    Returns:
      (best_place_dict or None, best_match_score, best_name_score, best_distance_m)
    """
    candidates = find_candidate_places(fhrs_row, places)
    if not candidates:
        return None, 0.0, 0.0, None

    best_place = None
    best_score = -1.0
    best_name_score = 0.0
    best_distance = None

    for p in candidates:
        combined, name_sim, dist_m = compute_match_score(fhrs_row, p)
        if dist_m is not None and dist_m > MAX_DISTANCE_METERS:
            continue  # too far away
        if combined > best_score:
            best_score = combined
            best_name_score = name_sim
            best_distance = dist_m
            best_place = p

    if best_score < MIN_MATCH_SCORE:
        return None, best_score, best_name_score, best_distance

    return best_place, best_score, best_name_score, best_distance


# ---------------- MAIN ----------------

def main():
    print("Loading Google places...")
    places = load_places(PLACES_CSV)
    print(f"Loaded {len(places)} Google places.")

    print("Loading FHRS data...")
    fhrs_rows = load_fhrs(FHRS_CSV)
    print(f"Loaded {len(fhrs_rows)} FHRS rows.")

    matched_rows = []

    for idx, row in enumerate(fhrs_rows, start=1):
        if idx % 500 == 0:
            print(f"Matching FHRS row {idx}/{len(fhrs_rows)}...")

        best_place, match_score, name_score, distance_m = match_one_fhrs(row, places)

        out = dict(row)  # start with all FHRS columns
        out["matched"] = bool(best_place)
        out["match_score"] = round(match_score, 3)
        out["match_name_score"] = round(name_score, 1)
        out["match_distance_m"] = round(distance_m, 1) if distance_m is not None else ""

        if best_place:
            out["google_place_id"] = best_place.get("place_id", "")
            out["google_name"] = best_place.get("name", "")
            out["google_address"] = best_place.get("address", "")
            out["google_rating"] = best_place.get("rating", "")
            out["google_num_reviews"] = best_place.get("num_reviews", "")
            out["google_food_types"] = best_place.get("food_types", "")
            out["google_price_level"] = best_place.get("price_level", "")
        else:
            out["google_place_id"] = ""
            out["google_name"] = ""
            out["google_address"] = ""
            out["google_rating"] = ""
            out["google_num_reviews"] = ""
            out["google_food_types"] = ""
            out["google_price_level"] = ""

        matched_rows.append(out)

    # Write output
    print(f"Writing output to {OUTPUT_CSV}...")
    if not matched_rows:
        print("No rows to write.")
        return

    fieldnames = list(matched_rows[0].keys())
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(matched_rows)

    n_matched = sum(1 for r in matched_rows if r["matched"])
    print(f"Done. Matched {n_matched} / {len(matched_rows)} FHRS rows "
          f"({n_matched / max(1, len(matched_rows)):.1%}).")


if __name__ == "__main__":
    main()
