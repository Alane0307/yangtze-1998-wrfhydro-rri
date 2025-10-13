#!/bin/bash
set -euo pipefail

# ===== Config =====
BASE_ROOT="$HOME/yangtze-1998-wrfhydro-rri"
ISD_INDEX_URL="https://www.ncei.noaa.gov/data/global-hourly/archive/isd/"
DOC_URL="https://www.ncei.noaa.gov/data/global-hourly/doc"
START_YEAR=1901
END_YEAR=2025

RAW_DIR="$BASE_ROOT/data/isd/raw"
META_DIR="$BASE_ROOT/data/isd/metadata"
REPORT_DIR="$BASE_ROOT/data/isd/reports"
LOGFILE="$REPORT_DIR/download_isd_$(date +%Y%m%d_%H%M).log"

mkdir -p "$RAW_DIR" "$META_DIR" "$REPORT_DIR"

echo "=== ISD download started at $(date) ===" | tee -a "$LOGFILE"
echo "[Dirs] RAW_DIR=$RAW_DIR  META_DIR=$META_DIR  REPORT_DIR=$REPORT_DIR" | tee -a "$LOGFILE"

# ----- Step A: 下载 metadata 文档（有更新才覆盖）-----
echo "[Docs] Fetching ISD docs into $META_DIR ..." | tee -a "$LOGFILE"
wget -N -P "$META_DIR" \
  "$DOC_URL/CSV_HELP.pdf" \
  "$DOC_URL/isd-format-document.pdf" \
  "$DOC_URL/sample.csv" 2>&1 | tee -a "$LOGFILE"

# ----- Step B: 抓取索引，提取每年最新版文件名 -----
echo "[Index] Fetching index page: $ISD_INDEX_URL" | tee -a "$LOGFILE"
INDEX_HTML="$(mktemp)"
# 用 wget 获取目录索引 HTML
wget -q -O "$INDEX_HTML" "$ISD_INDEX_URL"

# 函数：给定年份，返回该年 最新的 isd_YYYY_c*.tar.gz 文件名
latest_file_for_year () {
  local year="$1"
  # 从索引中抓出该年所有 tar.gz 链接，选“按文件名排序最后一个”（时间戳越新，名字越大）
  # 目录索引通常形如包含 href="isd_1901_c20180826T025524.tar.gz"
  grep -oE "isd_${year}_c[0-9T]+\.tar\.gz" "$INDEX_HTML" \
    | sort -V \
    | tail -n 1
}

# ----- Step C: 逐年下载（断点续传，可重复跑）-----
for (( y=$START_YEAR; y<=$END_YEAR; y++ )); do
  FILE="$(latest_file_for_year "$y" || true)"
  if [[ -z "${FILE}" ]]; then
    echo "[Warn] No file found for year $y on index. Skipping." | tee -a "$LOGFILE"
    continue
  fi
  URL="${ISD_INDEX_URL}${FILE}"
  DEST="${RAW_DIR}/${FILE}"

  if [[ -f "$DEST" ]]; then
    echo "[✓] Exists: $FILE (skip)" | tee -a "$LOGFILE"
    continue
  fi

  echo "[↓] Downloading $URL" | tee -a "$LOGFILE"
  # --continue 断点续传；--tries 重试；--timeout 超时；--show-progress 进度条
  wget --continue --tries=10 --timeout=30 --quiet --show-progress \
       -O "$DEST" "$URL" 2>&1 | tee -a "$LOGFILE"

  # 简单校验：非空且为 gzip 文件头
  if file "$DEST" | grep -qEi 'gzip compressed data'; then
    echo "[✓] Done: $FILE" | tee -a "$LOGFILE"
  else
    echo "[✗] Invalid file, removing: $FILE" | tee -a "$LOGFILE"
    rm -f "$DEST"
  fi
done

rm -f "$INDEX_HTML"
echo "=== ISD download finished at $(date) ===" | tee -a "$LOGFILE"

