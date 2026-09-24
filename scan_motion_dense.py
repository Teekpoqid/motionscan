"""Dense, hardware-accelerated motion scan: decodes at a fixed sample rate (default 2fps)
using GPU hwaccel decode+scale (CUDA on the 3090 box, QSV on the Intel Ultra box), so it
sees more of the video than the keyframe-only scan at the cost of more decode work.

Usage:
    python scan_motion_dense.py "C:\\path\\to\\videos" --hwaccel cuda --out dense_results.csv
    python scan_motion_dense.py "C:\\path\\to\\videos" --hwaccel qsv  --out dense_results.csv   # on the Intel box
"""
import argparse
import csv
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from motion_common import build_dense_cmd, find_ffmpeg, iter_video_files, run_and_score


def scan_one(ffmpeg_bin, root, path, w, h, fps, hwaccel, diff_threshold, frac_threshold, timeout, vaapi_device):
    cmd = build_dense_cmd(ffmpeg_bin, path, w, h, fps, hwaccel, vaapi_device=vaapi_device)
    res = run_and_score(cmd, w, h, diff_threshold, frac_threshold, timeout_sec=timeout)
    res["file"] = str(path)
    res["rel_path"] = str(path.relative_to(root))
    res["size_bytes"] = path.stat().st_size
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder")
    ap.add_argument("--ext", default="mkv,mp4")
    ap.add_argument("--no-recursive", action="store_true")
    ap.add_argument("--hwaccel", choices=["none", "cuda", "qsv", "vaapi"], default="cuda")
    ap.add_argument("--vaapi-device", default="/dev/dri/renderD128", help="VA-API render node (Linux/Docker, --hwaccel vaapi)")
    ap.add_argument("--fps", type=float, default=2.0, help="sampling rate for the dense scan")
    ap.add_argument("--scale-w", type=int, default=160)
    ap.add_argument("--scale-h", type=int, default=90)
    ap.add_argument("--diff-threshold", type=float, default=2.0)
    ap.add_argument("--frac-threshold", type=float, default=0.02)
    ap.add_argument("--workers", type=int, default=3, help="concurrent ffmpeg processes -- consumer GPUs cap concurrent decode sessions (~3-5), raise for --hwaccel none/qsv")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--out", default="dense_results.csv")
    args = ap.parse_args()

    ffmpeg_bin = find_ffmpeg()
    root = Path(args.folder)
    exts = tuple(e.strip().lstrip(".") for e in args.ext.split(","))
    files = sorted(iter_video_files(root, exts=exts, recursive=not args.no_recursive))
    if not files:
        print(f"No files with extensions {exts} found under {root}")
        return

    print(f"Scanning {len(files)} files (dense, hwaccel={args.hwaccel}, {args.fps}fps) with {args.workers} workers...")
    t0 = time.monotonic()
    rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {
            pool.submit(scan_one, ffmpeg_bin, root, p, args.scale_w, args.scale_h, args.fps,
                        args.hwaccel, args.diff_threshold, args.frac_threshold, args.timeout,
                        args.vaapi_device): p
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
