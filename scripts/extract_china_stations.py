#!/usr/bin/env python3
"""
Incrementally extract Chinese (CH*) station CSVs from a huge GHCN-Daily tar.gz archive
without loading the full file list into memory.

Usage:
  python extract_china_stations.py \
      --tar ~/data/ghcnd/daily-summaries-latest.tar.gz \
      --out ~/data/ghcnd/raw_china

This script:
  - Streams through the tar file entry by entry (no full list in memory)
  - Only extracts filenames starting with 'CH' (e.g., CHM00054511.csv)
  - Creates the output folder if it doesn't exist
  - Prints progress every 100 files
"""

import argparse
import tarfile
import os

def extract_china_stations(tar_path: str, out_dir: str, prefix: str = "CH"):
    os.makedirs(out_dir, exist_ok=True)
    count_total = 0
    count_extracted = 0

    with tarfile.open(tar_path, "r:gz") as tar:
        for member in tar:
            count_total += 1
            name = os.path.basename(member.name)
            if not name.lower().endswith(".csv"):
                continue
            if name.startswith(prefix):   # China stations
                tar.extract(member, path=out_dir)
                count_extracted += 1
                if count_extracted % 100 == 0:
                    print(f"[INFO] Extracted {count_extracted} files...")
            # optional: break early for test
            # if count_extracted >= 500: break

    print(f"=== Done ===")
    print(f"Total entries scanned: {count_total}")
    print(f"Extracted {count_extracted} CSVs to: {out_dir}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stream extract CH* CSVs from huge GHCN-Daily tar.gz")
    parser.add_argument("--tar", required=True, help="Path to daily-summaries-latest.tar.gz")
    parser.add_argument("--out", required=True, help="Output directory for extracted CH* CSVs")
    parser.add_argument("--prefix", default="CH", help="Station ID prefix to extract (default=CH)")
    args = parser.parse_args()

    extract_china_stations(args.tar, args.out, args.prefix)
