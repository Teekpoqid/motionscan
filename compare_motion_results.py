"""Compares two result CSVs (e.g. from scan_motion_fast.py and scan_motion_dense.py)
produced against the SAME folder, matched by relative path, and reports where the two
methods agree/disagree so you can validate the fast scan before trusting it at scale.

Usage:
    python compare_motion_results.py fast_results.csv dense_results.csv --out comparison.csv
"""
import argparse
import csv
from pathlib import Path


def load(path):
    with open(path, newline="") as f:
        return {row["rel_path"]: row for row in csv.DictReader(f)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("a", help="first results CSV (e.g. fast_results.csv)")
    ap.add_argument("b", help="second results CSV (e.g. dense_results.csv)")
    ap.add_argument("--out", default="comparison.csv")
    args = ap.parse_args()

    a = load(args.a)
    b = load(args.b)

    only_a = sorted(set(a) - set(b))
    only_b = sorted(set(b) - set(a))
    shared = sorted(set(a) & set(b))

    agree, disagree = [], []
    for rel in shared:
        ra, rb = a[rel], b[rel]
        row = {
            "rel_path": rel,
            "a_classification": ra["classification"],
            "b_classification": rb["classification"],
            "a_motion_fraction": ra["motion_fraction"],
            "b_motion_fraction": rb["motion_fraction"],
            "a_frames_sampled": ra["frames_sampled"],
            "b_frames_sampled": rb["frames_sampled"],
            "a_scan_seconds": ra["scan_seconds"],
            "b_scan_seconds": rb["scan_seconds"],
        }
        (agree if ra["classification"] == rb["classification"] else disagree).append(row)

    disagree.sort(key=lambda r: r["rel_path"])
    agree.sort(key=lambda r: r["rel_path"])

    fieldnames = ["rel_path", "a_classification", "b_classification", "a_motion_fraction",
                  "b_motion_fraction", "a_frames_sampled", "b_frames_sampled",
                  "a_scan_seconds", "b_scan_seconds"]
    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in disagree + agree:
            w.writerow(r)

    total = len(shared)
    print(f"Compared {args.a} (A) vs {args.b} (B)")
    print(f"  shared files: {total}")
    if only_a:
        print(f"  only in A (missing from B): {len(only_a)} -> {only_a[:10]}{' ...' if len(only_a) > 10 else ''}")
    if only_b:
        print(f"  only in B (missing from A): {len(only_b)} -> {only_b[:10]}{' ...' if len(only_b) > 10 else ''}")
    if total:
        print(f"  agree: {len(agree)} ({100 * len(agree) / total:.1f}%)")
        print(f"  disagree: {len(disagree)} ({100 * len(disagree) / total:.1f}%)")
    a_total_t = sum(float(r["scan_seconds"]) for r in a.values())
    b_total_t = sum(float(r["scan_seconds"]) for r in b.values())
    print(f"  total scan time -- A: {a_total_t:.1f}s, B: {b_total_t:.1f}s")

    if disagree:
        print("\nDisagreements:")
        for r in disagree:
            print(f"  {r['rel_path']}: A={r['a_classification']}({r['a_motion_fraction']}) "
                  f"B={r['b_classification']}({r['b_motion_fraction']})")

    print(f"\nWrote {args.out} (disagreements listed first)")


if __name__ == "__main__":
    main()
