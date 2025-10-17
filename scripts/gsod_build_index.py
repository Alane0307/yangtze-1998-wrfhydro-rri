#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
从 GSOD 目录按年扫描站点 CSV，只读首行拿到 LATITUDE/LONGITUDE，
筛到给定 BBOX 内，输出每年的站点索引：
  station_id, lon, lat, country

- 数据目录已改为 /data/gsod/（自动兼容含/不含 extracted/）
- 新增国家代码 country（优先自动从 /data/gsod/metadata/isd-history.csv 解析；
  也可用 --country-map 手动提供 station_id,country 的CSV）

示例：
  python gsod_build_index.py --years 1929-2025
  python gsod_build_index.py --years 1931,1954,1998 --bbox 85.5 130.0 18.0 40.0
  python gsod_build_index.py --years 1950-1960 --country-map /path/to/sid_country.csv
"""

import os, sys, csv, argparse, glob
import pandas as pd

# ===== 路径与窗口设置 =====
# 输出目录维持不变（如需改到 /data/ 下也可自行调整）
OUT_DIR   = os.path.expanduser("/data/gsod/index")

# 兼容两种常见结构：/data/gsod/extracted/<year>/*.csv 或 /data/gsod/<year>/*.csv
GSOD_BASE_CANDIDATES = ["/data/gsod/extracted", "/data/gsod"]

# 默认大窗口（与既有脚本一致）
DEFAULT_BBOX = dict(lon_min=85.5, lon_max=130.0, lat_min=18.0, lat_max=40.0)

def ensure_dir(p): os.makedirs(p, exist_ok=True)

def parse_years(spec: str):
    years = set()
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if "-" in chunk:
            a,b = chunk.split("-",1)
            years.update(range(int(a), int(b)+1))
        else:
            years.add(int(chunk))
    return sorted(y for y in years if 1900 <= y <= 2100)

def in_bbox(lat, lon, bbox):
    return (bbox["lat_min"] <= lat <= bbox["lat_max"]) and (bbox["lon_min"] <= lon <= bbox["lon_max"])

def read_first_latlon(csv_path):
    # 仅取头一行，且只读两列，加速
    try:
        df = pd.read_csv(csv_path, nrows=1, usecols=["LATITUDE","LONGITUDE"])
        if df.empty: return None
        lat = float(df.iloc[0]["LATITUDE"])
        lon = float(df.iloc[0]["LONGITUDE"])
        return lat, lon
    except Exception:
        return None

def find_year_dir(y: int):
    for base in GSOD_BASE_CANDIDATES:
        ydir = os.path.join(base, str(y))
        if os.path.isdir(ydir):
            return ydir
    return None

def load_country_map(path_hint: str = None):
    """优先尝试读取 isd-history.csv（需包含列：USAF, WBAN, CTRY），
       组合 6位USAF + 5位WBAN 作为 GSOD 11位站号，映射到 CTRY。
       若找不到有效文件，返回空映射。"""
    candidates = []
    if path_hint:
        candidates.append(path_hint)
    candidates += [
        "/data/gsod/metadata/isd-history.csv",
        "/data/gsod/metadata/isd_history.csv",
        "/data/isd/metadata/isd-history.csv",
        "/data/isd/metadata/isd_history.csv",
    ]
    for p in candidates:
        if p and os.path.isfile(p):
            try:
                df = pd.read_csv(p)
                # 允许不同大小写
                upcols = {c.upper(): c for c in df.columns}
                if not {"USAF","WBAN","CTRY"}.issubset(upcols.keys()):
                    continue
                usa = df[upcols["USAF"]].astype(str).str.zfill(6)
                wba = df[upcols["WBAN"]].astype(str).str.zfill(5)
                sid = usa + wba
                ctry = df[upcols["CTRY"]].astype(str)
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
    args = ap.parse_args()

    bbox = DEFAULT_BBOX if args.bbox is None else dict(
        lon_min=args.bbox[0], lon_max=args.bbox[1], lat_min=args.bbox[2], lat_max=args.bbox[3]
    )
    years = parse_years(args.years)
    ensure_dir(OUT_DIR)

    # 先尝试自动加载 ISD 历史表
    country_map = load_country_map()

    # 若用户显式提供自定义映射，则覆盖
    if args.country_map:
        try:
            dfm = pd.read_csv(args.country_map)
            if {"station_id","country"}.issubset(dfm.columns):
                country_map = dict(zip(dfm["station_id"].astype(str), dfm["country"].astype(str)))
            else:
                print(f"[warn] --country-map 缺少 station_id/country 列：{args.country_map}")
        except Exception as e:
            print(f"[warn] --country-map 读取失败：{e}")

    for y in years:
        ydir = find_year_dir(y)
        if not ydir:
            print(f"[warn] missing folder for year {y} under {GSOD_BASE_CANDIDATES}")
            continue

        rows = []
        # 每个站一个 CSV，文件名即 11 位站号，如 03075099999.csv
        for fp in glob.glob(os.path.join(ydir, "*.csv")):
            sid = os.path.splitext(os.path.basename(fp))[0]
            latlon = read_first_latlon(fp)
            if latlon is None:
                continue
            lat, lon = latlon
            if in_bbox(lat, lon, bbox):
                cc = country_map.get(sid, "")
                rows.append((sid, lon, lat, cc))

        out_csv = os.path.join(OUT_DIR, f"gsod_index_{y}.csv")
        with open(out_csv, "w", newline="", encoding="utf-8") as fw:
            w = csv.writer(fw)
            w.writerow(["station_id","lon","lat","country"])
            w.writerows(rows)

        print(f"[index] {y}: kept {len(rows)} stations in bbox -> {out_csv}")

if __name__ == "__main__":
    main()
