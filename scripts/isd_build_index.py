#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
从 ISD 目录按年扫描站点 CSV，只读首行拿到 LAT/LON，筛到给定 BBOX 内，
输出每年的站点索引：station_id, lon, lat, country

- 数据目录：优先 /data/isd/extracted/<year>/*.csv，其次 /data/isd/<year>/*.csv
- 国家代码 country：自动从 isd-history(.csv/.txt) 解析（USAF+WBAN→CTRY），
  也可用 --country-map 手动提供 station_id,country 的 CSV

示例：
  python isd_build_index.py --years 1929-2025
  python isd_build_index.py --years 1931,1954,1998 --bbox 85.5 130.0 18.0 40.0
  python isd_build_index.py --years 1950-1960 --country-map /path/to/sid_country.csv
"""

import os, sys, csv, argparse, glob, re
import pandas as pd

# ===== 路径与窗口设置 =====
OUT_DIR = os.path.expanduser("/data/isd/index")
ISD_BASE_CANDIDATES = ["/data/isd/extracted", "/data/isd"]

DEFAULT_BBOX = dict(lon_min=85.5, lon_max=130.0, lat_min=18.0, lat_max=40.0)

def ensure_dir(p): os.makedirs(p, exist_ok=True)

def parse_years(spec: str):
    years = set()
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if "-" in chunk:
            a, b = chunk.split("-", 1)
            years.update(range(int(a), int(b) + 1))
        else:
            years.add(int(chunk))
    return sorted(y for y in years if 1900 <= y <= 2100)

def in_bbox(lat, lon, bbox):
    return (bbox["lat_min"] <= lat <= bbox["lat_max"]) and (bbox["lon_min"] <= lon <= bbox["lon_max"])

# 允许多种列名：ISD/GSOD 提取后列名常见有 LATITUDE/LONGITUDE 或 LAT/LON
LAT_CANDIDATES = ["LATITUDE", "LAT", "latitude", "lat"]
LON_CANDIDATES = ["LONGITUDE", "LON", "longitude", "lon"]

def read_first_latlon(csv_path):
    try:
        # 只读首行，先探测有哪些列
        head = pd.read_csv(csv_path, nrows=1)
        if head.empty:
            return None
        cols = {c.lower(): c for c in head.columns}
        lat_col = next((cols[c.lower()] for c in LAT_CANDIDATES if c.lower() in cols), None)
        lon_col = next((cols[c.lower()] for c in LON_CANDIDATES if c.lower() in cols), None)
        if not lat_col or not lon_col:
            return None
        lat = float(head.iloc[0][lat_col])
        lon = float(head.iloc[0][lon_col])
        return lat, lon
    except Exception:
        return None

def find_year_dir(y: int):
    for base in ISD_BASE_CANDIDATES:
        ydir = os.path.join(base, str(y))
        if os.path.isdir(ydir):
            return ydir
    return None

def normalize_sid_from_filename(fp: str):
    """
    期望文件名形如 46764099999.csv 或 46764099999_1931.csv
    取去掉扩展名后的第一个下划线段作为 station_id。
    """
    base = os.path.splitext(os.path.basename(fp))[0]
    return base.split("_", 1)[0]

def load_country_map_from_isd_history(path_hint: str = None):
    """
    解析 isd-history（.csv 或 .txt）。需要列/字段：USAF, WBAN, CTRY。
    组合 6位USAF + 5位WBAN → 11位 station_id（与提取文件名一致）。
    """
    candidates = []
    if path_hint:
        candidates.append(path_hint)

    candidates += [
        # 常见命名与位置（csv 或 txt 都尝试）
        "/data/isd/metadata/isd-history.csv",
        "/data/isd/metadata/isd_history.csv",
        "/data/isd/metadata/isd-history.txt",
        "/data/isd/metadata/isd_history.txt",
        # 兼容从 gsod 侧放置的场景
        "/data/gsod/metadata/isd-history.csv",
        "/data/gsod/metadata/isd_history.csv",
        "/data/gsod/metadata/isd-history.txt",
        "/data/gsod/metadata/isd_history.txt",
    ]

    for p in candidates:
        if not (p and os.path.isfile(p)):
            continue
        try:
            if p.lower().endswith(".csv"):
                df = pd.read_csv(p)
            else:
                # isd-history.txt 是固定宽度/空白分隔的文本；用正则从每行提取关键字段
                rows = []
                with open(p, "r", encoding="utf-8", errors="ignore") as fr:
                    for line in fr:
                        # 粗犷匹配：USAF, WBAN, CTRY 常见为空白分隔；跳过标题/空行
                        m = re.search(r"(^|\s)(\d{1,6})\s+(\d{1,5})\s+.*?\s([A-Z]{2})\s", line)
                        if m:
                            usa, wba, ctry = m.group(2), m.group(3), m.group(4)
                            rows.append((usa, wba, ctry))
                if not rows:
                    continue
                df = pd.DataFrame(rows, columns=["USAF", "WBAN", "CTRY"])

            up = {c.upper(): c for c in df.columns}
            if not {"USAF", "WBAN", "CTRY"}.issubset(up.keys()):
                continue

            usa = df[up["USAF"]].astype(str).str.zfill(6)
            wba = df[up["WBAN"]].astype(str).str.zfill(5)
            sid = usa + wba
            ctry = df[up["CTRY"]].astype(str)
            return dict(zip(sid, ctry))
        except Exception:
            continue

    return {}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", required=True, help="例如 1929-2025 或 1931,1954,1998")
    ap.add_argument("--bbox", nargs=4, type=float, default=None,
                    help="lon_min lon_max lat_min lat_max（默认与既有脚本一致）")
    ap.add_argument("--country-map", default=None,
                    help="可选：自定义站点→国家映射CSV路径（两列：station_id,country）")
    ap.add_argument("--isd-history", default=None,
                    help="可选：显式指定 isd-history(.csv/.txt) 路径以解析国家代码")
    args = ap.parse_args()

    bbox = DEFAULT_BBOX if args.bbox is None else dict(
        lon_min=args.bbox[0], lon_max=args.bbox[1], lat_min=args.bbox[2], lat_max=args.bbox[3]
    )
    years = parse_years(args.years)
    ensure_dir(OUT_DIR)

    # 自动加载 isd-history（可被 --isd-history / --country-map 覆盖）
    country_map = load_country_map_from_isd_history(args.isd_history)

    # 若用户显式提供自定义映射，则覆盖
    if args.country_map:
        try:
            dfm = pd.read_csv(args.country_map)
            if {"station_id", "country"}.issubset(dfm.columns):
                country_map = dict(zip(dfm["station_id"].astype(str), dfm["country"].astype(str)))
            else:
                print(f"[warn] --country-map 缺少 station_id/country 列：{args.country_map}")
        except Exception as e:
            print(f"[warn] --country-map 读取失败：{e}")

    for y in years:
        ydir = find_year_dir(y)
        if not ydir:
            print(f"[warn] missing folder for year {y} under {ISD_BASE_CANDIDATES}")
            continue

        rows = []
        # 允许文件名两种风格：46764099999.csv 或 46764099999_1931.csv
        for fp in glob.glob(os.path.join(ydir, "*.csv")):
            sid = normalize_sid_from_filename(fp)
            latlon = read_first_latlon(fp)
            if latlon is None:
                continue
            lat, lon = latlon
            if in_bbox(lat, lon, bbox):
                cc = country_map.get(sid, "")
                rows.append((sid, lon, lat, cc))

        out_csv = os.path.join(OUT_DIR, f"isd_index_{y}.csv")
        with open(out_csv, "w", newline="", encoding="utf-8") as fw:
            w = csv.writer(fw)
            w.writerow(["station_id", "lon", "lat", "country"])
            w.writerows(rows)

        print(f"[index] {y}: kept {len(rows)} stations in bbox -> {out_csv}")

if __name__ == "__main__":
    main()
