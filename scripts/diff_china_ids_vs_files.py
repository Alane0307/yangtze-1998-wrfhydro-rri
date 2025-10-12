import os
import re
import csv
from typing import Dict, Tuple

# === Config ===
BASE_DIR = os.path.expanduser('~/data/ghcnd')
META_FILE = os.path.join(BASE_DIR, 'metadata', 'ghcnd-stations.txt')
CHINA_IDS_FILE = os.path.join(BASE_DIR, 'metadata', 'china_station_ids.txt')
FILES_DIR = os.path.join(BASE_DIR, 'china_allstations')  # folder with copied station CSVs
OUT_DIR = os.path.join(BASE_DIR, 'metadata')
REPORT_CSV = os.path.join(OUT_DIR, 'china_diff_report.csv')
MISSING_TXT = os.path.join(OUT_DIR, 'china_missing_ids.txt')
EXTRA_TXT = os.path.join(OUT_DIR, 'china_extra_ids.txt')
MATCHED_TXT = os.path.join(OUT_DIR, 'china_matched_ids.txt')

os.makedirs(OUT_DIR, exist_ok=True)

# === Helpers ===

def _safe_float(x: str):
    try:
        return float(x)
    except Exception:
        return None


def parse_stations_with_names(meta_path: str) -> Dict[str, Tuple[str, float, float]]:
    """Return dict: ID -> (NAME, LAT, LON)
    Robust to varying whitespace by first trying fixed-width for name,
    then falling back to regex tokenization.
    """
    id2meta: Dict[str, Tuple[str, float, float]] = {}
    with open(meta_path, 'r', encoding='utf-8', errors='ignore') as f:
        for raw in f:
            line = raw.rstrip('\n')
            if not line or len(line) < 11:
                continue
            # Attempt 1: fixed-width based on NOAA doc (ID[0:11], LAT[12:20], LON[21:30], ELEV[31:37], STATE[38:40], NAME[41:71])
            try:
                sid = line[0:11].strip()
                lat = _safe_float(line[12:20].strip())
                lon = _safe_float(line[21:30].strip())
                name = line[41:71].strip()
                if sid and lat is not None and lon is not None:
                    id2meta[sid] = (name, lat, lon)
                    continue
            except Exception:
                pass

            # Attempt 2: regex split, reconstruct name from remaining tokens
            parts = re.split(r"\s+", line.strip())
            if len(parts) >= 4:
                sid = parts[0]
                lat = _safe_float(parts[1])
                lon = _safe_float(parts[2])
                # elevation may be parts[3]; state may be parts[4]; name starts at 5 or 4
                # Try to detect if parts[4] looks like a 2-letter state code; if not, include in name
                start_idx_for_name = 5 if len(parts) > 5 else 4
                name = " ".join(parts[start_idx_for_name:]) if len(parts) > start_idx_for_name else ""
                if sid and (lat is not None) and (lon is not None):
                    id2meta[sid] = (name, lat, lon)
    return id2meta


def read_id_list(path: str):
    ids = []
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            s = line.strip()
            if s:
                ids.append(s)
    return ids


def list_file_ids(folder: str):
    ids = []
    for fn in os.listdir(folder):
        if fn.lower().endswith('.csv'):
            ids.append(fn[:-4])
    return ids


# === Load data ===
id2meta = parse_stations_with_names(META_FILE)
china_ids = set(read_id_list(CHINA_IDS_FILE))
file_ids = set(list_file_ids(FILES_DIR))

# === Diff sets ===
matched = sorted(china_ids & file_ids)
missing = sorted(china_ids - file_ids)  # expected from metadata but csv not present
extra   = sorted(file_ids - china_ids)  # csv present but not in china_ids list

# === Write plain text lists ===
with open(MATCHED_TXT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(matched))
with open(MISSING_TXT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(missing))
with open(EXTRA_TXT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(extra))

# === Build CSV report with names ===
# Columns: ID, STATUS, NAME, LAT, LON
rows = []
for sid in matched:
    nm, lat, lon = id2meta.get(sid, ("", None, None))
    rows.append([sid, 'OK', nm, lat, lon])
for sid in missing:
    nm, lat, lon = id2meta.get(sid, ("", None, None))
    rows.append([sid, 'MISSING', nm, lat, lon])
for sid in extra:
    nm, lat, lon = id2meta.get(sid, ("", None, None))
    rows.append([sid, 'EXTRA', nm, lat, lon])

with open(REPORT_CSV, 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['ID', 'STATUS', 'NAME', 'LAT', 'LON'])
    w.writerows(rows)

# === Console summary ===
print(f"China IDs in metadata: {len(china_ids)}")
print(f"CSV files in {FILES_DIR}: {len(file_ids)}")
print(f"Matched: {len(matched)}  |  Missing: {len(missing)}  |  Extra: {len(extra)}")
print(f"Report written: {REPORT_CSV}")
