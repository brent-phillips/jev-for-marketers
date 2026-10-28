#!/usr/bin/env python3
"""Score a jev_batch.py results file against an answer key.

Usage:
    python3 score_results.py RESULTS.csv ANSWER_KEY.csv [--id lead_id]

The answer key has one row per record, an id column, and one column per question
holding the expected answer. Expected values can be:
    core               exact answer
    core|adjacent      any of these counts as right
    *                  don't score this one
Optional columns `difficulty` and `what_it_tests` are used in the report.

The report answers the questions that matter before you automate anything:
    - How often is Jev right overall, and on the easy vs tricky rows?
    - When Jev was confident (auto band), how often was it right?
    - When it was wrong, did the review/human bands catch it?
"""
import argparse
import csv
from collections import defaultdict


def norm(value):
    # "yes (0.97)" -> "yes"; "1.60 (High)" -> "1.60"
    return (value or "").strip().split(" ")[0].lower()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results")
    ap.add_argument("answer_key")
    ap.add_argument("--id", default="lead_id", help="id column shared by both files (default: lead_id)")
    args = ap.parse_args()

    results = {r[args.id]: r for r in csv.DictReader(open(args.results, encoding="utf-8-sig"))}
    key_rows = list(csv.DictReader(open(args.answer_key, encoding="utf-8-sig")))
    meta = {args.id, "difficulty", "what_it_tests"}
    questions = [c for c in key_rows[0].keys() if c not in meta]

    stats = defaultdict(lambda: defaultdict(lambda: [0, 0]))  # q -> bucket -> [right, total]
    misses = []
    for k in key_rows:
        rid = k[args.id]
        res = results.get(rid)
        if res is None:
            print(f"Missing from results: {rid}")
            continue
        diff = k.get("difficulty", "all") or "all"
        for q in questions:
            expected = (k[q] or "").strip().lower()
            if expected in ("", "*"):
                continue
            got = norm(res.get(q))
            band = res.get(f"{q}_band", "?")
            ok = got in expected.split("|")
            for bucket in ("all", diff, f"band:{band}"):
                stats[q][bucket][0] += ok
                stats[q][bucket][1] += 1
            if not ok:
                misses.append((rid, q, expected, got, band, res.get(f"{q}_confidence", ""), k.get("what_it_tests", "")))

    def pct(rt):
        r, t = rt
        return f"{r}/{t} ({100 * r / t:.0f}%)" if t else "-"

    print("\nACCURACY BY QUESTION")
    print(f"{'question':<16}{'overall':<14}{'easy':<14}{'trap':<14}{'auto band':<14}{'review':<14}{'human':<14}")
    for q in questions:
        s = stats[q]
        print(f"{q:<16}{pct(s['all']):<14}{pct(s['easy']):<14}{pct(s['trap']):<14}"
              f"{pct(s['band:auto']):<14}{pct(s['band:review']):<14}{pct(s['band:human']):<14}")

    caught = sum(1 for m in misses if m[4] in ("review", "human"))
    print(f"\nWRONG ANSWERS: {len(misses)}  |  caught by review/human band: {caught}  |  slipped through on auto: {len(misses) - caught}")
    if misses:
        print("\nDETAIL (auto-band misses first; these are the ones that would have gone out unchecked)")
        for rid, q, exp, got, band, conf, why in sorted(misses, key=lambda m: m[4] != "auto"):
            print(f"  {rid} {q}: expected {exp}, got {got} ({band}, {conf})  - {why}")

    rows_by_action = defaultdict(int)
    for r in results.values():
        rows_by_action[r.get("row_action", "?")] += 1
    print("\nROWS BY ACTION: " + ", ".join(f"{a}: {n}" for a, n in sorted(rows_by_action.items())))
    print("\nWhat to look at: the auto-band accuracy. If auto-band misses aren't near zero, raise `act` or tighten the criteria before automating.")


if __name__ == "__main__":
    main()
