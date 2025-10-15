#!/usr/bin/env python3
import tarfile
import os
import glob
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

# 输入与输出目录
RAW_DIR = os.path.expanduser("~/yangtze-1998-wrfhydro-rri/data/isd/raw")
TARGET_DIR = os.path.expanduser("~/yangtze-1998-wrfhydro-rri/data/isd/extracted")
LOG_FILE = os.path.join(TARGET_DIR, "unpack_log.txt")

os.makedirs(TARGET_DIR, exist_ok=True)

def extract_tar(file_path):
    """安全解压单个tar.gz文件"""
    try:
        year = os.path.basename(file_path).split("_")[1]
        out_dir = os.path.join(TARGET_DIR, year)
        os.makedirs(out_dir, exist_ok=True)

        # 若目标目录已有文件，跳过
        if any(os.scandir(out_dir)):
            return f"{year}: skipped (already extracted)"

        with tarfile.open(file_path, "r:gz") as tar:
            tar.extractall(out_dir)
        return f"{year}: done ({len(os.listdir(out_dir))} files)"
    except Exception as e:
        return f"{file_path}: ERROR - {e}"

def main():
    tar_files = sorted(glob.glob(os.path.join(RAW_DIR, "isd_*.tar.gz")))
    if not tar_files:
        print("No .tar.gz files found in", RAW_DIR)
        return

    start = datetime.now()
    print(f"Starting extraction of {len(tar_files)} files...")

    with ThreadPoolExecutor(max_workers=6) as executor:  # 可调整线程数
        futures = {executor.submit(extract_tar, f): f for f in tar_files}
        with open(LOG_FILE, "a") as log:
            log.write(f"\n--- Extraction started {start} ---\n")
            for future in as_completed(futures):
                result = future.result()
                print(result)
                log.write(result + "\n")

    print("All done in", datetime.now() - start)

if __name__ == "__main__":
    main()

