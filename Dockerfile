# Dockerized QSV (Intel iGPU) motion scanner -- for the Intel Ultra 275K box.
# Uses VA-API as the path to QuickSync: stock Ubuntu ffmpeg supports -hwaccel vaapi
# out of the box, unlike -hwaccel qsv which needs the full Intel oneVPL/MediaSDK stack.
#
# Build:
#   docker build -f Dockerfile.qsv -t motion-scan-qsv .
#
# Run (Linux host, or WSL2 with the iGPU passed through to the WSL2 kernel):
#   docker run --rm -it --device /dev/dri:/dev/dri \
#     -v "/path/to/videos:/videos" \
#     -e HWACCEL=vaapi -e VIDEOS_PATH=/videos \
#     motion-scan-qsv
#
# Sanity-check the device is visible/usable first:
#   docker run --rm --device /dev/dri:/dev/dri --entrypoint vainfo motion-scan-qsv
#
# All settings are environment variables (see docker-entrypoint.sh) so this same image
# is drivable from docker-compose or Unraid's Config UI, not just raw CLI flags.

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    intel-media-va-driver-non-free \
    vainfo \
    python3 \
    python3-numpy \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY motion_common.py scan_motion_dense.py scan_motion_fast.py compare_motion_results.py docker-entrypoint.sh ./
RUN chmod +x docker-entrypoint.sh

ENTRYPOINT ["./docker-entrypoint.sh"]
