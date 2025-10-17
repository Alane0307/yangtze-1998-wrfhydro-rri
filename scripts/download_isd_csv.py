#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import sys
import time
import tarfile
import shutil
import logging
import argparse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ----------------- 可配置参数 -----------------
BASE_ROOT = os.path.expanduser("/data")
CSV_BASE_URL = "https://www.ncei.noaa.gov/data/global-hourly/archive/csv/"

START_YEAR_DEFAULT = 1901
END_YEAR_DEFAULT = 2025

# 并发下载线程数（根据网络与磁盘情况微调）
MAX_WORKERS = 4

# 单文件下载重试与超时
RETRIES = 8
TIMEOUT = (10, 60)  # (connect timeout, read timeout) 秒

# 速率限制：每下完一个文件后小憩（秒），减轻服务器压力
PAUSE_BETWEEN_FILES = 1.5

# ----------------- 路径 -----------------
RAW_DIR = os.path.join(BASE_ROOT, "isd/csv_raw")
EXTRACT_DIR = os.path.join(BASE_ROOT, "isd/csv_extracted")
META_DIR = os.path.join(BASE_ROOT, "isd/metadata")
REPORT_DIR = os.path.join(BASE_ROOT, "isd/reports")

os.makedirs(RAW_DIR, exist_ok=True)
os.makedirs(EXTRACT_DIR, exist_ok=True)
os.makedirs(META_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)

LOG_FILE = os.path.join(REPORT_DIR, f"download_isd_csv_{datetime.now():%Y%m%d_%H%M%S}.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)]
)

# ----------------- HTTP 会话（带重试） -----------------
def make_session() -> requests.Session:
    sess = requests.Session()
    retry = Retry(
        total=RETRIES,
        connect=RETRIES,
        read=RETRIES,
        status=RETRIES,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=MAX_WORKERS, pool_maxsize=MAX_WORKERS*2)
    sess.mount("http://", adapter)
    sess.mount("https://", adapter)
    # 如需强制 IPv4，可在系统层面做解析或使用代理；requests 本身不直接强制族别
    sess.headers.update({"User-Agent": "ISD-CSV-Downloader/1.0"})
    return sess

SESSION = make_session()

# ----------------- 工具函数 -----------------
def fetch_directory_index() -> str:
    """抓取 CSV 目录索引页面 HTML（一次），用于解析每年真实文件名"""
    logging.info("Fetching CSV index: %s", CSV_BASE_URL)
    r = SESSION.get(CSV_BASE_URL, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text

def pick_filename_for_year(index_html: str, year: int) -> str | None:
    """
    在目录索引中挑选某年的最新压缩包文件名。
    优先匹配 `YYYY.tar.gz`；其次兼容 `isd_YYYY_...csv.tar.gz`。
    """
    m1 = re.findall(rf'>(?:\s*)({year}\.tar\.gz)<', index_html)
    if m1:
        # 目录可能列出多次，取最后一个（通常是正确的）
        return sorted(set(m1))[-1]
    m2 = re.findall(rf'>(?:\s*)(isd_{year}_[\w\-]*csv\.tar\.gz)<', index_html)
    if m2:
        return sorted(set(m2))[-1]
    return None

def human_size(num_bytes: int) -> str:
    for unit in ["B","KB","MB","GB","TB"]:
        if num_bytes < 1024:
            return f"{num_bytes:.1f}{unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f}PB"

def download_with_resume(url: str, dest_path: str) -> None:
    """
    断点续传下载：若存在 .part 则以 Range 续下；完成后原子移动为最终文件名。
    """
    tmp_path = dest_path + ".part"
    downloaded = 0
    if os.path.exists(tmp_path):
        downloaded = os.path.getsize(tmp_path)

    headers = {}
    if downloaded > 0:
        headers["Range"] = f"bytes={downloaded}-"

    # 先探测总大小
    head = SESSION.head(url, timeout=TIMEOUT, allow_redirects=True)
    head.raise_for_status()
    total = int(head.headers.get("Content-Length", "0"))
    accept_ranges = head.headers.get("Accept-Ranges", "none")

    mode = "ab" if downloaded > 0 and accept_ranges != "none" else "wb"
    if mode == "wb":
        downloaded = 0  # 不能 Range 时重下

    with SESSION.get(url, headers=headers, stream=True, timeout=TIMEOUT) as r:
        r.raise_for_status()
        os.makedirs(os.path.dirname(tmp_path), exist_ok=True)
        with open(tmp_path, mode) as f:
            for chunk in r.iter_content(chunk_size=1024*1024):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
        # 简单校验大小（有些服务器不报 Content-Length，这里容忍 total==0）
        if total and downloaded < total:
            raise IOError(f"Incomplete download for {os.path.basename(dest_path)}: "
                          f"{human_size(downloaded)} / {human_size(total)}")

    os.replace(tmp_path, dest_path)

def verify_gzip(path: str) -> bool:
    try:
        with tarfile.open(path, "r:gz") as tar:
            # 试读头部
            tar.getmembers()[:1]
        return True
    except Exception as e:
        logging.warning("Gzip verification failed for %s: %s", os.path.basename(path), e)
        return False

def extract_year_tar(tar_path: str, year_dir: str) -> int:
    """
    解压到该年份目录；若目录已有文件，视为已完成（跳过）。
    返回解压出的 CSV 文件数量。
    """
    os.makedirs(year_dir, exist_ok=True)
    if any(os.scandir(year_dir)):
        # 已解压过
        return len([p for p in os.listdir(year_dir) if p.endswith(".csv")])

    count = 0
    with tarfile.open(tar_path, "r:gz") as tar:
        def is_within_directory(directory, target):
            abs_directory = os.path.abspath(directory)
            abs_target = os.path.abspath(target)
            return os.path.commonpath([abs_directory]) == os.path.commonpath([abs_directory, abs_target])
        # 安全解压（防止路径穿越）
        for member in tar.getmembers():
            member_path = os.path.join(year_dir, member.name)
            if not is_within_directory(year_dir, member_path):
                raise Exception("Unsafe path in tar: " + member.name)
        tar.extractall(year_dir)
    # 统计
    for name in os.listdir(year_dir):
        if name.endswith(".csv"):
            count += 1
    return count

# ----------------- 主流程 -----------------
def process_one_year(year: int, index_html: str) -> tuple[int, str]:
    """
    下载并解压某一年。返回 (year, message)。
    """
    try:
        fn = pick_filename_for_year(index_html, year)
        if not fn:
            return year, f"[Warn] {year}: Not found in index. Skipped."

        url = CSV_BASE_URL + fn
        raw_path = os.path.join(RAW_DIR, fn)
        year_dir = os.path.join(EXTRACT_DIR, str(year))

        if os.path.exists(year_dir) and any(os.scandir(year_dir)):
            return year, f"[=] {year}: already extracted ({len(os.listdir(year_dir))} files)"

        if not os.path.exists(raw_path):
            logging.info("[↓] %s: %s", year, url)
            download_with_resume(url, raw_path)
        else:
            logging.info("[=] %s: found existing %s", year, os.path.basename(raw_path))

        if not verify_gzip(raw_path):
            # 损坏则删除，提示重下
            sz = os.path.getsize(raw_path) if os.path.exists(raw_path) else 0
            try:
                os.remove(raw_path)
            except OSError:
                pass
            return year, f"[✗] {year}: corrupted archive removed (size was {human_size(sz)}). Re-run to retry."

        n_csv = extract_year_tar(raw_path, year_dir)
        # 可选：节省空间时删除原 tar
        # os.remove(raw_path)

        time.sleep(PAUSE_BETWEEN_FILES)
        return year, f"[✓] {year}: extracted {n_csv} CSV files"
    except Exception as e:
        return year, f"[ERR] {year}: {e}"

def main():
    parser = argparse.ArgumentParser(description="Download & extract NOAA ISD CSV archives by year.")
    parser.add_argument("--start", type=int, default=START_YEAR_DEFAULT, help="start year (default 1901)")
    parser.add_argument("--end", type=int, default=END_YEAR_DEFAULT, help="end year (default 2025)")
    parser.add_argument("--workers", type=int, default=MAX_WORKERS, help="parallel download workers")
    parser.add_argument("--keep-tar", action="store_true", help="keep .tar.gz after extraction")
    args = parser.parse_args()

    start, end = args.start, args.end
    if start > end:
        start, end = end, start

    logging.info("=== ISD CSV download started: %s ===", datetime.now().strftime("%F %T"))
    logging.info("[Years] %d..%d  [Workers]=%d", start, end, args.workers)
    logging.info("[Dirs] RAW=%s  EXTRACT=%s  META=%s  REPORT=%s", RAW_DIR, EXTRACT_DIR, META_DIR, REPORT_DIR)

    # 抓一次索引，后续直接解析
    index_html = fetch_directory_index()

    # 并行执行
    years = list(range(start, end + 1))
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(process_one_year, y, index_html): y for y in years}
        for fut in as_completed(futs):
            year = futs[fut]
            _, msg = fut.result()
            logging.info(msg)
            results.append((year, msg))

    # 可选：删除已解压完成的 tar 以省空间
    if not args.keep_tar:
        for y in years:
            # 两种可能的命名
            pat1 = os.path.join(RAW_DIR, f"{y}.tar.gz")
            pat2_candidates = [p for p in os.listdir(RAW_DIR) if re.fullmatch(rf"isd_{y}_[\w\-]*csv\.tar\.gz", p or "")]
            for p in [pat1] + [os.path.join(RAW_DIR, c) for c in pat2_candidates]:
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except OSError:
                        pass

    logging.info("=== ISD CSV download finished: %s ===", datetime.now().strftime("%F %T"))
    logging.info("Log file: %s", LOG_FILE)

if __name__ == "__main__":
    main()
df 