"""Fast, CPU-only motion scan: decodes ONLY keyframes (-skip_frame nokey), skipping
~95%+ of frames at the decoder level. No GPU required -- works on either machine.

Usage:
    python scan_motion_fast.py "C:\\path\\to\\videos" --out fast_results.csv
"""
import argparse
import csv
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from motion_common import build_keyframe_cmd, find_ffmpeg, iter_video_files, run_and_score


def scan_one(ffmpeg_bin, root, path, w, h, diff_threshold, frac_threshold, timeout):
    cmd = build_keyframe_cmd(ffmpeg_bin, path, w, h)
    res = run_and_score(cmd, w, h, diff_threshold, frac_threshold, timeout_sec=timeout)
    res["file"] = str(path)
    res["rel_path"] = str(path.relative_to(root))
    res["size_bytes"] = path.stat().st_size
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder")
    ap.add_argument("--ext", default="mkv,mp4", help="comma-separated extensions (default: mkv,mp4)")
    ap.add_argument("--no-recursive", action="store_true")
    ap.add_argument("--scale-w", type=int, default=160)
    ap.add_argument("--scale-h", type=int, default=90)
    ap.add_argument("--diff-threshold", type=float, default=2.0, help="mean abs pixel diff (0-255) that counts a keyframe pair as 'changed'")
    ap.add_argument("--frac-threshold", type=float, default=0.02, help="fraction of changed keyframe pairs needed to call a file 'motion'")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--timeout", type=int, default=600, help="per-file ffmpeg timeout in seconds")
    ap.add_argument("--out", default="fast_results.csv")
    args = ap.parse_args()

    ffmpeg_bin = find_ffmpeg()
    root = Path(args.folder)
    exts = tuple(e.strip().lstrip(".") for e in args.ext.split(","))
    files = sorted(iter_video_files(root, exts=exts, recursive=not args.no_recursive))
    if not files:
        print(f"No files with extensions {exts} found under {root}")
        return

    print(f"Scanning {len(files)} files (keyframes-only, CPU) with {args.workers} workers...")
    t0 = time.monotonic()
    rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {
            pool.submit(scan_one, ffmpeg_bin, root, p, args.scale_w, args.scale_h,
                        args.diff_threshold, args.frac_threshold, args.timeout): p
            for p in files
        }
        done = 0
        for fut in as_completed(futs):
            row = fut.result()
            rows.append(row)
            done += 1
            print(f"[{done}/{len(files)}] {row['rel_path']}: {row['classification']} "
                  f"(motion_frac={row['motion_fraction']:.3f}, frames={row['frames_sampled']}, "
                  f"{row['scan_seconds']}s){' ERROR: ' + row['error'] if row['error'] else ''}")

    rows.sort(key=lambda r: r["rel_path"])
    fieldnames = ["rel_path", "file", "size_bytes", "frames_sampled", "mean_diff", "max_diff",
                  "motion_fraction", "classification", "scan_seconds", "error"]
    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r[k] for k in fieldnames})

    elapsed = time.monotonic() - t0
    no_motion = sum(1 for r in rows if r["classification"] == "no_motion")
    motion = sum(1 for r in rows if r["classification"] == "motion")
    errors = sum(1 for r in rows if r["classification"] == "error")
    print(f"\nDone in {elapsed:.1f}s. motion={motion} no_motion={no_motion} errors={errors}. Wrote {args.out}")


if __name__ == "__main__":
    main()
