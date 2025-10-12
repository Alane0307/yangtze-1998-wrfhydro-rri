#!/usr/bin/env python3
"""
Safely extract *all* files from a huge GHCN-Daily tar.gz archive
without blowing up WSL memory or re-extracting existing files.

Features:
- Streams tar entries one by one (no full index in memory)
- Skips files already present in the output directory
- Prints progress every 1000 files
- Can be resumed anytime (idempotent)
"""

import argparse
import tarfile
import os
from pathlib import Path

def extract_all_safe(tar_path: str, out_dir: str):
    tar_path = Path(tar_path).expanduser()
    out_dir = Path(out_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    count_total = 0
    count_extracted = 0
    count_skipped = 0

    with tarfile.open(tar_path, "r:gz") as tar:
        for member in tar:
            count_total += 1
            # skip directories
            if not member.isfile():
                continue
            name = os.path.basename(member.name)
            if not name.lower().endswith(".csv"):
                continue

            dest_file = out_dir / name
            if dest_file.exists():
                count_skipped += 1
                continue

            try:
                tar.extract(member, path=out_dir)
                count_extracted += 1
            except Exception as e:
                print(f"[WARN] Failed to extract {name}: {e}")

            if count_total % 1000 == 0:
                print(f"[INFO] Scanned {count_total:,} entries | Extracted {count_extracted:,} | Skipped {count_skipped:,}")

    print("\n=== Extraction finished ===")
    print(f"Scanned:    {count_total:,}")
    print(f"Extracted:  {count_extracted:,}")
    print(f"Skipped:    {count_skipped:,}")
    print(f"Output dir: {out_dir}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stream-extract all CSVs from a huge tar.gz archive safely")
    parser.add_argument("--tar", required=True, help="Path to the .tar.gz file (e.g., daily-summaries-latest.tar.gz)")
    parser.add_argument("--out", required=True, help="Output directory (existing files will be skipped)")
    args = parser.parse_args()

    extract_all_safe(args.tar, args.out)
