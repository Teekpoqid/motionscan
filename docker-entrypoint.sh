#!/bin/sh
# Reads configuration from environment variables (so this image is drivable from
# Unraid's Config UI, which only supports env vars/paths/devices -- not CLI args)
# and execs the matching scan script. Any extra "$@" args are passed straight through
# and win, so `docker run ... --diff-threshold 3.0` still works for manual overrides.
set -e

MODE="${MODE:-dense}"
FOLDER="${VIDEOS_PATH:-/videos}"
SCALE_W="${SCALE_W:-160}"
SCALE_H="${SCALE_H:-90}"
DIFF_THRESHOLD="${DIFF_THRESHOLD:-2.0}"
FRAC_THRESHOLD="${FRAC_THRESHOLD:-0.02}"
WORKERS="${WORKERS:-6}"
TIMEOUT="${TIMEOUT:-600}"
EXTENSIONS="${EXTENSIONS:-mkv,mp4}"

RECURSIVE_FLAG=""
if [ "${RECURSIVE:-true}" = "false" ]; then
  RECURSIVE_FLAG="--no-recursive"
fi

if [ "$MODE" = "fast" ]; then
  OUT_FILE="${OUT_FILE:-fast_results.csv}"
  exec python3 scan_motion_fast.py "$FOLDER" \
    --scale-w "$SCALE_W" --scale-h "$SCALE_H" \
    --diff-threshold "$DIFF_THRESHOLD" --frac-threshold "$FRAC_THRESHOLD" \
    --workers "$WORKERS" --timeout "$TIMEOUT" --ext "$EXTENSIONS" \
    $RECURSIVE_FLAG --out "$FOLDER/$OUT_FILE" "$@"
else
  HWACCEL="${HWACCEL:-qsv}"
  FPS="${FPS:-2.0}"
  VAAPI_DEVICE="${VAAPI_DEVICE:-/dev/dri/renderD128}"
  OUT_FILE="${OUT_FILE:-dense_results_${HWACCEL}.csv}"
  exec python3 scan_motion_dense.py "$FOLDER" \
    --hwaccel "$HWACCEL" --fps "$FPS" \
    --scale-w "$SCALE_W" --scale-h "$SCALE_H" \
    --diff-threshold "$DIFF_THRESHOLD" --frac-threshold "$FRAC_THRESHOLD" \
    --workers "$WORKERS" --timeout "$TIMEOUT" --ext "$EXTENSIONS" \
    --vaapi-device "$VAAPI_DEVICE" \
    $RECURSIVE_FLAG --out "$FOLDER/$OUT_FILE" "$@"
fi
