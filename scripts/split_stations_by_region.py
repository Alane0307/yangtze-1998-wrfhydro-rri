#!/usr/bin/env python3
"""
Split GHCN-Daily station CSVs into two geographic groups using simple lon/lat boxes:

  1) Yangtze basin bbox + degree buffer (for precipitation-focused work)
  2) An enlarged East/Central China big window (for temperature/pressure background)

No shapefiles, no projections, no geo libs.

It reads station coordinates from metadata/ghcnd-stations.txt,
matches them to station CSV files in raw/ (<STATION_ID>.csv),
copies the selected files into splits/ folders,
and writes summary + missing-in-raw reports for both target regions.
"""

from __future__ import annotations
import os
import re
import shutil
from typing import Dict, Tuple, Iterable, List

# =========================
# ======= CONFIGURE =======
# =========================
BASE_DIR   = os.path.expanduser('~/yangtze-1998-wrfhydro-rri/data/ghcnd')
META_FILE  = os.path.join(BASE_DIR, 'metadata', 'ghcnd-stations.txt')
RAW_DIR    = os.path.join(BASE_DIR, 'raw')            # where <ID>.csv live
OUT_DIR    = os.path.join(BASE_DIR, 'splits')         # output root

# Degree-based buffer for the Yangtze bbox (use 1.5–2.0 as a starting point)
BUFFER_DEG = 1.5

# Rough envelope of the Yangtze basin (lon_min, lon_max, lat_min, lat_max)
YANGTZE_BBOX = (90.0, 123.0, 24.0, 34.5)

# Enlarged big region bbox (as discussed)
# (lon_min, lon_max, lat_min, lat_max)
BIG_REGION_BBOX = (90.0, 130.0, 18.0, 38.0)

# Output folders
OUT_BASIN   = os.path.join(OUT_DIR, 'stations_yangtze_plus_buffer')
OUT_BIGWIN  = os.path.join(OUT_DIR, 'stations_big_window')
REPORT_DIR  = os.path.join(OUT_DIR, 'reports')

os.makedirs(OUT_BASIN, exist_ok=True)
os.makedirs(OUT_BIGWIN, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)

# =========================
# ====== UTILITIES ========
# =========================
NUM_RE = re.compile(r'^[+-]?(?:\d+\.?\d*|\.\d+)$')

def _safe_float(s: str):
    s = s.strip()
    if NUM_RE.match(s):
        try:
            return float(s)
        except Exception:
            return None
    return None

def parse_stations(meta_path: str) -> Dict[str, Tuple[float, float]]:
    """
    Parse metadata/ghcnd-stations.txt into {ID: (lat, lon)} robustly.
    Try fixed-width first; if that fails, fall back to whitespace split.
    """
    id2ll: Dict[str, Tuple[float, float]] = {}
    with open(meta_path, 'r', encoding='utf-8', errors='ignore') as f:
        for raw in f:
            line = raw.rstrip('\n')
            if not line or len(line) < 11:
                continue
            # Attempt 1: fixed-width columns per NOAA doc
            try:
                sid = line[0:11].strip()
                lat = _safe_float(line[12:20])
                lon = _safe_float(line[21:30])
                if sid and (lat is not None) and (lon is not None):
                    id2ll[sid] = (lat, lon)
                    continue
            except Exception:
                pass
            # Attempt 2: whitespace split
            parts = re.split(r'\s+', line.strip())
            if len(parts) >= 3:
                sid = parts[0]
                lat = _safe_float(parts[1])
                lon = _safe_float(parts[2])
                if sid and (lat is not None) and (lon is not None):
                    id2ll[sid] = (lat, lon)
    return id2ll

def station_ids_from_raw(raw_dir: str) -> Iterable[str]:
    for fn in os.listdir(raw_dir):
        if fn.lower().endswith('.csv'):
            yield fn[:-4]

def expand_bbox(bbox, buffer_deg: float):
    lon_min, lon_max, lat_min, lat_max = bbox
    return (lon_min - buffer_deg, lon_max + buffer_deg,
            lat_min - buffer_deg, lat_max + buffer_deg)

def select_ids_by_bbox(id2ll: Dict[str, Tuple[float, float]], bbox) -> set[str]:
    """Return station IDs with (lon,lat) within bbox = (lon_min, lon_max, lat_min, lat_max)."""
    lon_min, lon_max, lat_min, lat_max = bbox
    selected = set()
    for sid, (lat, lon) in id2ll.items():
        if (lon_min <= lon <= lon_max) and (lat_min <= lat <= lat_max):
            selected.add(sid)
    return selected

def copy_selected(raw_dir: str, out_dir: str, ids: Iterable[str]) -> int:
    ids_set = set(ids)
    copied = 0
    for sid in ids_set:
        src = os.path.join(raw_dir, f'{sid}.csv')
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(out_dir, f'{sid}.csv'))
            copied += 1
    return copied

def write_list(path: str, items: List[str]):
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(items))

# =========================
# ========= MAIN ==========
# =========================
if __name__ == '__main__':
    # Load metadata & available files
    id2ll = parse_stations(META_FILE)
    file_ids = set(station_ids_from_raw(RAW_DIR))

    # Build simple bboxes
    basin_bbox         = YANGTZE_BBOX
    basin_buffered_box = expand_bbox(YANGTZE_BBOX, BUFFER_DEG)
    bigwin_bbox        = BIG_REGION_BBOX

    # Select targets
    ids_basin_target   = select_ids_by_bbox(id2ll, basin_buffered_box)
    ids_bigwin_target  = select_ids_by_bbox(id2ll, bigwin_bbox)

    # Determine which exist in raw
    ids_basin_to_copy  = ids_basin_target & file_ids
    ids_bigwin_to_copy = ids_bigwin_target & file_ids

    # Missing-in-raw (relative to target regions)
    missing_basin = sorted(ids_basin_target - file_ids)
    missing_big   = sorted(ids_bigwin_target - file_ids)
    write_list(os.path.join(REPORT_DIR, 'missing_in_raw_yangtze_plus_buffer.txt'), missing_basin)
    write_list(os.path.join(REPORT_DIR, 'missing_in_raw_big_window.txt'), missing_big)

    # Copy
    n1 = copy_selected(RAW_DIR, OUT_BASIN, ids_basin_to_copy)
    n2 = copy_selected(RAW_DIR, OUT_BIGWIN, ids_bigwin_to_copy)

    # Reports
    try:
        import pandas as pd
        pd.Series(sorted(ids_basin_to_copy)).to_csv(
            os.path.join(REPORT_DIR, 'ids_yangtze_plus_buffer.csv'),
            index=False, header=['ID']
        )
        pd.Series(sorted(ids_bigwin_to_copy)).to_csv(
            os.path.join(REPORT_DIR, 'ids_big_window.csv'),
            index=False, header=['ID']
        )
    except Exception:
        # pandas is optional; silently skip CSV if not installed
        pass

    with open(os.path.join(REPORT_DIR, 'summary.txt'), 'w', encoding='utf-8') as f:
        f.write(f'Total stations in metadata: {len(id2ll)}\n')
        f.write(f'Files available in RAW_DIR: {len(file_ids)}\n')
        f.write(f'Target (Yangtze+buffer bbox): {len(ids_basin_target)} | Copied: {n1} | Missing in raw: {len(missing_basin)}\n')
        f.write(f'Target (Big window bbox):     {len(ids_bigwin_target)} | Copied: {n2} | Missing in raw: {len(missing_big)}\n')

    print('=== Split complete ===')
    print(f'Yangtze+buffer target: {len(ids_basin_target)} | Copied: {n1} | Missing in raw: {len(missing_basin)} -> {OUT_BASIN}')
    print(f'Big window target:     {len(ids_bigwin_target)} | Copied: {n2} | Missing in raw: {len(missing_big)} -> {OUT_BIGWIN}')
    print(f'Reports in: {REPORT_DIR}')
