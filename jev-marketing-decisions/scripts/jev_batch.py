#!/usr/bin/env python3
"""Run a Jev decision recipe over every row of a CSV.

Usage:
    python3 jev_batch.py RECIPE.json INPUT.csv [-o OUTPUT.csv] [--model jev-latest] [--limit N] [--dry-run]

Needs TYPESAFE_API_KEY in your environment (get one at https://console.typesafe.ai/keys).
Standard library only, no installs needed.

For each row it:
  1. builds the state from the recipe's state_columns (only what the decision needs),
  2. asks every question in the recipe in one Jev call,
  3. puts each answer in a band (auto / review / human) using the recipe's thresholds,
  4. writes the answers, confidences, bands and the model version to the output CSV.
"""
import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
BAND_ORDER = {"auto": 2, "review": 1, "human": 0}


def build_state(row, columns):
    lines = []
    for col in columns:
        value = (row.get(col) or "").strip()
        lines.append(f"{col}: {value if value else '(not provided)'}")
    return "\n".join(lines)


def call_jev(payload, api_key, retries=3):
    data = json.dumps(payload).encode("utf-8")
    for attempt in range(retries):
        req = urllib.request.Request(
            ENDPOINT,
            data=data,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise SystemExit(f"Jev returned HTTP {e.code}: {body[:500]}")
        except urllib.error.URLError as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise SystemExit(f"Could not reach {ENDPOINT}: {e.reason}")


def band_for(answer, bands):
    """Return (value, confidence, band) for one answer."""
    act, review = bands.get("act", 0.85), bands.get("review", 0.6)
    kind = answer.get("type")
    if kind == "noul":
        p = answer.get("noul", 0.0)
        # A noul is a probability the statement is true. Far from 0.5 either way = sure.
        conf = max(p, 1 - p)
        value = "yes" if p >= 0.5 else "no"
        return f"{value} ({p:.2f})", conf, ("auto" if conf >= act else "review" if conf >= review else "human")
    conf = answer.get("confidence")
    conf = 0.0 if conf is None else conf
    if kind == "choice":
        value = answer.get("choice")
    elif kind == "score":
        score = answer.get("score", 0.0)
        legend = answer.get("legend", {})
        nearest = str(int(round(score)))
        value = f"{score:.2f} ({legend.get(nearest, nearest)})"
    else:
        value = json.dumps(answer)
    return value, conf, ("auto" if conf >= act else "review" if conf >= review else "human")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("recipe")
    ap.add_argument("input_csv")
    ap.add_argument("-o", "--output", help="output CSV (default: INPUT_jev.csv)")
    ap.add_argument("--model", help="override the recipe's model, e.g. jev-latest")
    ap.add_argument("--limit", type=int, help="only run the first N rows (good for a first test)")
    ap.add_argument("--dry-run", action="store_true", help="print the first request and stop; no API call")
    args = ap.parse_args()

    recipe = json.load(open(args.recipe, encoding="utf-8"))
    questions = recipe["questions"]
    columns = recipe["state_columns"]
    bands = recipe.get("bands", {})
    model = args.model or recipe.get("model", "jev-latest")

    rows = list(csv.DictReader(open(args.input_csv, encoding="utf-8-sig")))
    if args.limit:
        rows = rows[: args.limit]
    missing = [c for c in columns if rows and c not in rows[0]]
    if missing:
        raise SystemExit(f"These state_columns aren't in the CSV: {missing}. Columns found: {list(rows[0].keys())}")

    if args.dry_run:
        payload = {"model": model, "state": build_state(rows[0], columns), "questions": questions}
        print(json.dumps(payload, indent=2))
        return

    api_key = os.environ.get("TYPESAFE_API_KEY")
    if not api_key:
        raise SystemExit("Set TYPESAFE_API_KEY first. Get a key at https://console.typesafe.ai/keys")

    out_path = args.output or os.path.splitext(args.input_csv)[0] + "_jev.csv"
    q_names = list(questions.keys())
    extra = []
    for q in q_names:
        extra += [f"{q}", f"{q}_confidence", f"{q}_band"]
    fieldnames = list(rows[0].keys()) + extra + ["row_action", "jev_model"]

    counts = {"auto": 0, "review": 0, "human": 0}
    tokens = 0
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for i, row in enumerate(rows, 1):
            payload = {"model": model, "state": build_state(row, columns), "questions": questions}
            resp = call_jev(payload, api_key)
            answers = resp.get("answers", {})
            worst = "auto"
            for q in q_names:
                value, conf, band = band_for(answers.get(q, {}), bands)
                row[q], row[f"{q}_confidence"], row[f"{q}_band"] = value, f"{conf:.2f}", band
                if BAND_ORDER[band] < BAND_ORDER[worst]:
                    worst = band
            row["row_action"] = worst
            row["jev_model"] = resp.get("model", model)
            counts[worst] += 1
            tokens += resp.get("usage", {}).get("input_tokens", 0)
            writer.writerow(row)
            print(f"[{i}/{len(rows)}] {worst}", file=sys.stderr)

    cost = tokens / 1_000_000 * 0.042
    print(f"\nWrote {out_path}")
    print(f"Rows: {len(rows)} | auto: {counts['auto']} | review: {counts['review']} | human: {counts['human']}")
    print(f"Input tokens: {tokens:,} (about ${cost:.6f} at $0.042 per million; check current pricing)")


if __name__ == "__main__":
    main()
