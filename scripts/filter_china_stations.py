import os
import pandas as pd

# === Step 1: set paths ===
BASE_DIR = os.path.expanduser('~/data/ghcnd')
META_PATH = os.path.join(BASE_DIR, 'metadata', 'ghcnd-stations.txt')
RAW_DIR = os.path.join(BASE_DIR, 'raw')
CHINA_DIR = os.path.join(BASE_DIR, 'china_allstations')

os.makedirs(CHINA_DIR, exist_ok=True)

# === Step 2: read station metadata ===
# ghcnd-stations.txt is fixed-width, columns: ID, LAT, LON, ELEV, STATE, NAME...
cols = [(0, 11), (12, 20), (21, 30), (31, 37), (38, 40), (41, 71)]
names = ['ID', 'LAT', 'LON', 'ELEV', 'STATE', 'NAME']

df = pd.read_fwf(META_PATH, colspecs=cols, names=names, dtype=str)

# Clean and numeric conversions
df['LAT'] = df['LAT'].astype(float)
df['LON'] = df['LON'].astype(float)

# === Step 3: filter stations in China region ===
# Typical range: 18°N–54°N, 73°E–135°E
china_df = df[(df['LON'].between(73, 135)) & (df['LAT'].between(18, 54))]

# Additional filter: station ID starting with 'CH'
china_df = china_df[china_df['ID'].str.startswith('CH')]

print(f"Found {len(china_df)} stations likely in China region.")

# === Step 4: copy matching station CSV files ===
import shutil
count_copied = 0
for sid in china_df['ID']:
    src = os.path.join(RAW_DIR, f"{sid}.csv")
    dst = os.path.join(CHINA_DIR, f"{sid}.csv")
    if os.path.exists(src):
        shutil.copy(src, dst)
        count_copied += 1

print(f"Copied {count_copied} CSV files to {CHINA_DIR}.")

# === Step 5: report differences ===
expected = set(china_df['ID'])
existing = {f[:-4] for f in os.listdir(CHINA_DIR) if f.endswith('.csv')}
missing = expected - existing
extra = existing - expected

print(f"Missing (in metadata but no file): {len(missing)}")
print(f"Extra (copied but not listed): {len(extra)}")

if missing:
    with open(os.path.join(CHINA_DIR, 'missing_stations.txt'), 'w') as f:
        f.write('\n'.join(sorted(missing)))
if extra:
    with open(os.path.join(CHINA_DIR, 'extra_stations.txt'), 'w') as f:
        f.write('\n'.join(sorted(extra)))
