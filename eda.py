import csv

INPUT_FILE = "london_restaurants_with_fhrs.csv"

def main():
    total = 0
    matched = 0
    high_conf = 0

    with open(INPUT_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1

            fhrs_id = (row.get("fhrs_id") or "").strip()
            if fhrs_id:
                matched += 1

                # Optional: use the match_score we wrote out
                score_str = (row.get("match_score") or "").strip()
                try:
                    score = float(score_str)
                    if score >= 1.4:   # tweak threshold as you like
                        high_conf += 1
                except ValueError:
                    pass

    print(f"Total Google places: {total}")
    print(f"Matched to any FHRS record: {matched} ({matched/total*100:.1f}%)")

    if total > 0:
        print(f"High-confidence matches (score >= 1.4): "
              f"{high_conf} ({high_conf/total*100:.1f}%)")

if __name__ == "__main__":
    main()
