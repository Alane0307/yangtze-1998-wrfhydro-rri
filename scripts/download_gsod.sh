#!/bin/bash
set -e

# === Configuration ===
BASE_URL="https://www.ncei.noaa.gov/data/global-summary-of-the-day/archive"
TARGET_DIR="$HOME/yangtze-1998-wrfhydro-rri/data/gsod/raw"
REPORT_DIR="$HOME/yangtze-1998-wrfhydro-rri/data/gsod/reports"
START_YEAR=1929
END_YEAR=2025

mkdir -p "$TARGET_DIR" "$REPORT_DIR"

LOGFILE="$REPORT_DIR/download_log_$(date +%Y%m%d_%H%M).txt"

echo "=== GSOD bulk download started at $(date) ===" | tee -a "$LOGFILE"

for ((year=$START_YEAR; year<=$END_YEAR; year++)); do
    FILE="${year}.tar.gz"
    URL="${BASE_URL}/${FILE}"
    DEST="${TARGET_DIR}/${FILE}"

    # Skip existing
    if [[ -f "$DEST" ]]; then
        echo "[✓] ${FILE} already exists, skipping." | tee -a "$LOGFILE"
        continue
    fi

    echo "[↓] Downloading $URL ..." | tee -a "$LOGFILE"
    wget -q --show-progress --progress=bar:force:noscroll -O "$DEST" "$URL" || {
        echo "[✗] Failed: $URL" | tee -a "$LOGFILE"
        continue
    }

    echo "[✓] Completed: ${FILE}" | tee -a "$LOGFILE"
done

echo "=== All downloads completed at $(date) ===" | tee -a "$LOGFILE"

