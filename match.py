import csv
import math
import re
import difflib
from typing import Dict, List, Optional

# --------------- CONFIG ---------------

GOOGLE_CSV = "london_restaurants_grid.csv"
FHRS_CSV = "fhrs_london.csv"
OUTPUT_CSV = "london_restaurants_with_fhrs.csv"

# Max distance between Google place and FHRS venue to be considered (meters)
MAX_DISTANCE_METERS = 120.0

# Minimum name similarity (0–1) required
MIN_NAME_SIMILARITY = 0.70


# --------------- GEO HELPERS ---------------

def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Distance between two lat/lng points in meters.
    """
    R = 6371000.0  # earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


# --------------- STRING HELPERS ---------------

STOP_SUFFIXES = [" LTD", " LIMITED"]

def normalize_name(s: str) -> str:
    if not s:
        return ""
    s = s.upper()
    s = s.replace("&", " AND ")
    for suf in STOP_SUFFIXES:
        if s.endswith(suf):
            s = s[: -len(suf)]
    s = re.sub(r"[^A-Z0-9 ]+", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def name_similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


# --------------- DATA LOADERS ---------------

def load_csv(path: str) -> List[Dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def safe_float(v: str) -> Optional[float]:
    try:
        return float(v)
    except Exception:
        return None


# --------------- MATCHING ---------------

def match_one_place(
    place: Dict[str, str],
    fhrs_records: List[Dict[str, str]],
) -> Optional[Dict[str, str]]:
    """
    For a single Google place, find best FHRS match within spatial + name thresholds.
    Returns the FHRS row dict or None.
    """
    plat = safe_float(place.get("latitude", ""))
    plng = safe_float(place.get("longitude", ""))
    if plat is None or plng is None:
        return None

    g_name_norm = normalize_name(place.get("name", ""))

    best = None
    best_score = -1.0

    # Precompute rough degree filter to avoid computing Haversine for everything
    # ~1 degree lat ~ 111km
    max_deg = MAX_DISTANCE_METERS / 111_000.0

    for f in fhrs_records:
        flat = safe_float(f.get("latitude", ""))
        flng = safe_float(f.get("longitude", ""))
        if flat is None or flng is None:
            continue

        # quick bounding box filter
        if abs(flat - plat) > max_deg or abs(flng - plng) > max_deg:
            continue

        dist = haversine_m(plat, plng, flat, flng)
        if dist > MAX_DISTANCE_METERS:
            continue

        f_name_norm = normalize_name(f.get("business_name", ""))
        sim = name_similarity(g_name_norm, f_name_norm)

        if sim < MIN_NAME_SIMILARITY:
            continue

        # Combine similarity + distance into a simple score
        # 1 for perfect similarity + 1 for zero distance
        dist_component = max(0.0, 1.0 - dist / MAX_DISTANCE_METERS)
        score = sim + dist_component

        if score > best_score:
            best_score = score
            best = {
                **f,
                "_match_distance_m": dist,
                "_match_name_similarity": sim,
                "_match_score": score,
            }

    return best


def match_all(google_rows: List[Dict[str, str]], fhrs_rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    For each Google row, attach FHRS fields if a suitable match is found.
    """
    output_rows: List[Dict[str, str]] = []

    for idx, g in enumerate(google_rows, start=1):
        if idx % 50 == 0:
            print(f"Matching {idx}/{len(google_rows)}...")

        match = match_one_place(g, fhrs_rows)

        out = dict(g)  # start with all Google columns

        if match:
            out["fhrs_id"] = match.get("fhrs_id")
            out["fhrs_business_name"] = match.get("business_name")
            out["fhrs_rating_value"] = match.get("rating_value")
            out["fhrs_rating_date"] = match.get("rating_date")
            out["fhrs_postcode"] = match.get("postcode")
            out["fhrs_local_authority"] = match.get("local_authority_name")
            out["fhrs_hygiene_score"] = match.get("hygiene_score")
            out["fhrs_structural_score"] = match.get("structural_score")
            out["fhrs_confidence_in_management_score"] = match.get("confidence_in_management_score")
            out["fhrs_latitude"] = match.get("latitude")
            out["fhrs_longitude"] = match.get("longitude")
            out["match_distance_m"] = f"{match.get('_match_distance_m', 0):.2f}"
            out["match_name_similarity"] = f"{match.get('_match_name_similarity', 0):.3f}"
            out["match_score"] = f"{match.get('_match_score', 0):.3f}"
        else:
            out["fhrs_id"] = ""
            out["fhrs_business_name"] = ""
            out["fhrs_rating_value"] = ""
            out["fhrs_rating_date"] = ""
            out["fhrs_postcode"] = ""
            out["fhrs_local_authority"] = ""
            out["fhrs_hygiene_score"] = ""
            out["fhrs_structural_score"] = ""
            out["fhrs_confidence_in_management_score"] = ""
            out["fhrs_latitude"] = ""
            out["fhrs_longitude"] = ""
            out["match_distance_m"] = ""
            out["match_name_similarity"] = ""
            out["match_score"] = ""

        output_rows.append(out)

    return output_rows


# --------------- MAIN ---------------

def main():
    print("Loading Google CSV...")
    google_rows = load_csv(GOOGLE_CSV)
    print(f"Loaded {len(google_rows)} Google places.")

    print("Loading FHRS CSV...")
    fhrs_rows = load_csv(FHRS_CSV)
    print(f"Loaded {len(fhrs_rows)} FHRS establishments.")

    print("Matching Google places to FHRS establishments...")
    matched_rows = match_all(google_rows, fhrs_rows)

    # Collect all fieldnames (Google + FHRS)
    fieldnames = list(matched_rows[0].keys()) if matched_rows else []

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(matched_rows)

    print(f"\n✓ Wrote {len(matched_rows)} rows to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
