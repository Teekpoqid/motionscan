"""Shared frame-extraction and motion-scoring helpers for the scan scripts."""
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

VIDEO_EXTS_DEFAULT = ("mkv", "mp4")


def find_ffmpeg():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    # winget installs land under a versioned WinGet package folder; fall back to a search
    candidates = list(Path(r"C:\Users").glob(r"*\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg*\ffmpeg-*\bin\ffmpeg.exe"))
    if candidates:
        return str(candidates[0])
    sys.exit("ffmpeg not found on PATH. Install it (e.g. `winget install Gyan.FFmpeg`) and restart your shell.")


def iter_video_files(root, exts=VIDEO_EXTS_DEFAULT, recursive=True):
    root = Path(root)
    pattern_fn = root.rglob if recursive else root.glob
    seen = set()
    for ext in exts:
        for p in pattern_fn(f"*.{ext}"):
            if p not in seen:
                seen.add(p)
                yield p


def build_keyframe_cmd(ffmpeg_bin, path, w, h):
    """Software decode, but only decode keyframes (I-frames) -- skips the vast majority
    of frames at the demuxer/decoder level instead of decoding-then-discarding them."""
    return [
        ffmpeg_bin, "-nostdin", "-hide_banner", "-loglevel", "error",
        "-skip_frame", "nokey",
        "-i", str(path),
        "-an", "-sn",
        "-vf", f"scale={w}:{h}:flags=fast_bilinear,format=gray",
        "-fps_mode", "passthrough",
        "-f", "rawvideo", "-pix_fmt", "gray",
        "-",
    ]


def build_dense_cmd(ffmpeg_bin, path, w, h, fps, hwaccel, vaapi_device="/dev/dri/renderD128"):
    common_in = ["-nostdin", "-hide_banner", "-loglevel", "error"]
    if hwaccel == "cuda":
        return [
            ffmpeg_bin, *common_in,
            "-hwaccel", "cuda", "-hwaccel_output_format", "cuda",
            "-i", str(path),
            "-an", "-sn",
            "-vf", f"fps={fps},scale_cuda={w}:{h},hwdownload,format=nv12,extractplanes=y",
            "-f", "rawvideo", "-pix_fmt", "gray",
            "-",
        ]
    if hwaccel == "qsv":
        return [
            ffmpeg_bin, *common_in,
            "-hwaccel", "qsv", "-hwaccel_output_format", "qsv",
            "-i", str(path),
            "-an", "-sn",
            "-vf", f"fps={fps},vpp_qsv=w={w}:h={h},hwdownload,format=nv12,extractplanes=y",
            "-f", "rawvideo", "-pix_fmt", "gray",
            "-",
        ]
    if hwaccel == "vaapi":
        # Linux/Docker path to Intel QSV hardware -- goes through VA-API, which stock
        # ffmpeg builds (e.g. Ubuntu's apt package) support out of the box, unlike the
        # "qsv" hwaccel above which needs the full Intel oneVPL/MediaSDK stack compiled in.
        return [
            ffmpeg_bin, *common_in,
            "-hwaccel", "vaapi", "-hwaccel_device", vaapi_device, "-hwaccel_output_format", "vaapi",
            "-i", str(path),
            "-an", "-sn",
            "-vf", f"fps={fps},scale_vaapi=w={w}:h={h}:format=nv12,hwdownload,format=nv12,extractplanes=y",
            "-f", "rawvideo", "-pix_fmt", "gray",
            "-",
        ]
    # software fallback, no hwaccel
    return [
        ffmpeg_bin, *common_in,
        "-i", str(path),
        "-an", "-sn",
        "-vf", f"fps={fps},scale={w}:{h}:flags=fast_bilinear,format=gray",
        "-f", "rawvideo", "-pix_fmt", "gray",
        "-",
    ]


def run_and_score(cmd, w, h, diff_threshold, frac_threshold, timeout_sec=600):
    """Runs ffmpeg, reads raw gray8 frames from stdout, scores frame-to-frame motion."""
    frame_size = w * h
    start = time.monotonic()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    prev = None
    diffs = []
    frames_read = 0
    err = None
    try:
        while True:
            if time.monotonic() - start > timeout_sec:
                proc.kill()
                err = f"timeout after {timeout_sec}s"
                break
            chunk = proc.stdout.read(frame_size)
            if not chunk:
                break
            if len(chunk) < frame_size:
                break
            frames_read += 1
            frame = np.frombuffer(chunk, dtype=np.uint8).reshape(h, w).astype(np.int16)
            if prev is not None:
                diffs.append(float(np.abs(frame - prev).mean()))
            prev = frame
        proc.stdout.close()
        proc.wait(timeout=30)
    except Exception as e:
        err = err or str(e)
    finally:
        if proc.poll() is None:
            proc.kill()
    stderr_tail = b""
    try:
        stderr_tail = proc.stderr.read()
        proc.stderr.close()
    except Exception:
        pass
    elapsed = time.monotonic() - start

    if err is None and proc.returncode not in (0, None) and frames_read == 0:
        err = stderr_tail.decode(errors="replace").strip()[-500:] or f"ffmpeg exit {proc.returncode}"

    result = {
        "frames_sampled": frames_read,
        "mean_diff": float(np.mean(diffs)) if diffs else 0.0,
        "max_diff": float(np.max(diffs)) if diffs else 0.0,
        "motion_fraction": (sum(1 for d in diffs if d > diff_threshold) / len(diffs)) if diffs else 0.0,
        "scan_seconds": round(elapsed, 2),
        "error": err or "",
    }
    if err:
        result["classification"] = "error"
    elif frames_read < 2:
        result["classification"] = "insufficient_data"
    else:
        result["classification"] = "motion" if result["motion_fraction"] >= frac_threshold else "no_motion"
    return result
