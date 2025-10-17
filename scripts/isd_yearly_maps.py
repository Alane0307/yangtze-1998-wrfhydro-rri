#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, sys, math, argparse, glob
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import matplotlib.pyplot as plt

# ========= 路径与输出 =========
# 兼容 /data/isd/extracted/<year>/*.csv 与 /data/isd/<year>/*.csv
ISD_BASE_CANDIDATES = ["/data/isd/extracted", "/data/isd"]

# ISD 索引目录：与 isd_build_index.py 默认输出一致
INDEX_DIR = os.path.expanduser("/data/isd/index")

# 输出图路径（与 GSOD 版对应的 isd_maps 目录）
OUT_DIR = os.path.expanduser(
    "~/yangtze-1998-wrfhydro-rri/docs/figs/isd_maps"
)

# 默认 BBOX（与你既有脚本一致）
BBOX = dict(lon_min=85.5, lon_max=130.0, lat_min=18.0, lat_max=40.0)

# ========= 叠加用地理图层（与 GSOD 脚本保持一致的路径与风格）=========
YANGTZE_BASIN_UNION_SHP = os.path.expanduser(
    "/data/geodata/hydrobasins/yangtze_level5_union.shp"
)
YANGTZE_MAIN_GPKG = os.path.expanduser(
    "/data/geodata/hydrorivers/yangtze_mainstem.gpkg"
)
YANGTZE_MAIN_LAYER = "yangtze_mainstem"
YANGTZE_TRIB_GPKG = os.path.expanduser(
    "/data/geodata/hydrorivers/yangtze_major_tribs.gpkg"
)
YANGTZE_TRIB_LAYER = "yangtze_major_tribs"

NE_LAND_SHP = os.path.expanduser(
    "/data/geodata/natural_earth/ne_50m_land/ne_50m_land.shp"
)
NE_COUNTRY_SHP = os.path.expanduser(
    "/data/geodata/natural_earth/ne_50m_admin_0_countries/ne_50m_admin_0_countries.shp"
)

# ========= 绘图样式（与 GSOD 版保持一致）=========
DPI = 300
LAND_FC = "#f0efe8"
LAND_EC = "#c6c3b6"
COUNTRY_EC = "#8b8b8b"
BASIN_EC = "#2a6f97"
MAIN_EC = "#153f65"
TRIB_EC = "#4f86c6"
STATION_FC = "#d04e4e"
FIGSIZE = (8.5, 6.5)
COUNTRY_LW = 0.7
BASIN_LW = 1.4
MAIN_LW = 1.8
TRIB_LW = 1.2
STATION_MS = 8
STATION_ALPHA = 0.85

def ensure_dir(p): os.makedirs(p, exist_ok=True)

# ========= 底图缓存，与 GSOD 版一致 =========
class BaseLayers:
    def __init__(self):
        self.land=None; self.country=None; self.basin=None; self.main=None; self.trib=None
        self.china_poly=None  # 供空间回退判断使用

    def load(self):
        if os.path.exists(NE_LAND_SHP):
            self.land = gpd.read_file(NE_LAND_SHP); self.land = self._to_wgs84(self.land)
        else:
            print(f"[warn] land shp not found: {NE_LAND_SHP}")

        if os.path.exists(NE_COUNTRY_SHP):
            self.country = gpd.read_file(NE_COUNTRY_SHP); self.country = self._to_wgs84(self.country)
            # 预取中国多边形：优先 ADM0_A3 == "CHN"，回退到 NAME/NAME_EN == "China"
            try:
                cols = {c.lower(): c for c in self.country.columns}
                poly = None
                if "adm0_a3" in cols:
                    cand = self.country[self.country[cols["adm0_a3"]].astype(str).str.upper().eq("CHN")]
                    if not cand.empty: poly = cand.union_all()
                if poly is None:
                    for key in ["name_en", "name"]:
                        if key in cols:
                            cand = self.country[self.country[cols[key]].astype(str).str.upper().eq("CHINA")]
                            if not cand.empty: poly = cand.union_all(); break
                self.china_poly = poly
            except Exception as e:
                print(f"[warn] build china polygon failed: {e}")
        else:
            print(f"[warn] country shp not found: {NE_COUNTRY_SHP}")

        if YANGTZE_BASIN_UNION_SHP and os.path.exists(YANGTZE_BASIN_UNION_SHP):
            self.basin = gpd.read_file(YANGTZE_BASIN_UNION_SHP); self.basin = self._to_wgs84(self.basin)

        if YANGTZE_MAIN_GPKG and os.path.exists(YANGTZE_MAIN_GPKG):
            try:
                self.main = gpd.read_file(YANGTZE_MAIN_GPKG, layer=YANGTZE_MAIN_LAYER)
                self.main = self._to_wgs84(self.main)
            except Exception as e:
                print(f"[warn] load mainstem failed: {e}")

        if YANGTZE_TRIB_GPKG and os.path.exists(YANGTZE_TRIB_GPKG):
            try:
                self.trib = gpd.read_file(YANGTZE_TRIB_GPKG, layer=YANGTZE_TRIB_LAYER)
                self.trib = self._to_wgs84(self.trib)
            except Exception as e:
                print(f"[warn] load tribs failed: {e}")

    @staticmethod
    def _to_wgs84(gdf):
        try:
            if gdf.crs is None: gdf.set_crs(epsg=4326, inplace=True)
            else: gdf = gdf.to_crs(epsg=4326)
        except Exception:
            pass
        return gdf

BASE = BaseLayers()

# ========= 坐标轴风格（与 GSOD 版一致）=========
def _nice_step(span):
    raw = span / 6.0
    candidates = [0.25, 0.5, 1, 2, 2.5, 5]
    return min(candidates, key=lambda c: abs(c - raw))

def _setup_axes(ax, bbox):
    ax.set_xlim(bbox["lon_min"], bbox["lon_max"])
    ax.set_ylim(bbox["lat_min"], bbox["lat_max"])
    ax.set_aspect("equal", adjustable="box")
    lon_span = bbox["lon_max"] - bbox["lon_min"]
    lat_span = bbox["lat_max"] - bbox["lat_min"]
    ax.set_xticks(np.arange(math.ceil(bbox["lon_min"]), math.floor(bbox["lon_max"])+1e-6, _nice_step(lon_span)))
    ax.set_yticks(np.arange(math.ceil(bbox["lat_min"]), math.floor(bbox["lat_max"])+1e-6, _nice_step(lat_span)))
    ax.set_xlabel("Longitude (°E)")
    ax.set_ylabel("Latitude (°N)")

def draw_map(year, pts_lonlat, out_png, bbox, subtitle=None):
    ensure_dir(os.path.dirname(out_png))
    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)

    if BASE.land is not None and not BASE.land.empty:
        BASE.land.plot(ax=ax, facecolor=LAND_FC, edgecolor=LAND_EC, linewidth=0.4, zorder=0)
    if BASE.country is not None and not BASE.country.empty:
        BASE.country.plot(ax=ax, facecolor="none", edgecolor=COUNTRY_EC, linewidth=COUNTRY_LW, zorder=1)
    if BASE.basin is not None and not BASE.basin.empty:
        BASE.basin.boundary.plot(ax=ax, color=BASIN_EC, linewidth=BASIN_LW, zorder=2)
    if BASE.main is not None and not BASE.main.empty:
        BASE.main.plot(ax=ax, color=MAIN_EC, linewidth=MAIN_LW, zorder=3)
    if BASE.trib is not None and not BASE.trib.empty:
        BASE.trib.plot(ax=ax, color=TRIB_EC, linewidth=TRIB_LW, zorder=3)

    if pts_lonlat:
        gdf_pts = gpd.GeoDataFrame(geometry=[Point(x,y) for x,y in pts_lonlat], crs="EPSG:4326")
        gdf_pts.plot(ax=ax, marker="o", color=STATION_FC, markersize=STATION_MS, alpha=STATION_ALPHA, zorder=4)

    _setup_axes(ax, bbox)
    title = f"ISD Stations — {year}"
    if subtitle:
        title += f"\n{subtitle}"
    ax.set_title(title)

    from matplotlib.lines import Line2D
    handles, labels = [], []
    if pts_lonlat:
        handles.append(Line2D([], [], marker='o', color='none',
                              markerfacecolor=STATION_FC, markersize=STATION_MS/1.6))
        labels.append("ISD Station")
    if BASE.main is not None and not BASE.main.empty:
        handles.append(Line2D([], [], color=MAIN_EC, linewidth=MAIN_LW)); labels.append("Yangtze mainstem")
    if BASE.trib is not None and not BASE.trib.empty:
        handles.append(Line2D([], [], color=TRIB_EC, linewidth=TRIB_LW)); labels.append("Major tributaries")
    if BASE.basin is not None and not BASE.basin.empty:
        handles.append(Line2D([], [], color=BASIN_EC, linewidth=BASIN_LW)); labels.append("Yangtze basin boundary")
    if handles:
        ax.legend(handles, labels, loc="upper right", frameon=True, framealpha=0.9)

    plt.tight_layout()
    fig.savefig(out_png, bbox_inches="tight")
    plt.close(fig)

# ========= 数据加载 =========
def find_year_dir(y: int):
    for base in ISD_BASE_CANDIDATES:
        ydir = os.path.join(base, str(y))
        if os.path.isdir(ydir):
            return ydir
    return None

def load_points_from_index(y, bbox, china_codes):
    """优先用 ISD 索引（station_id, lon, lat, country）。
       返回：(bbox内所有点, bbox∩中国点) —— 都是 [(lon,lat), ...] 列表。"""
    f = os.path.join(INDEX_DIR, f"isd_index_{y}.csv")
    pts_all, pts_china = [], []
    if os.path.exists(f):
        df = pd.read_csv(f)
        has_country = "country" in df.columns
        # 先做 BBOX 收敛
        df = df[(df["lon"]>=bbox["lon_min"]) & (df["lon"]<=bbox["lon_max"]) &
                (df["lat"]>=bbox["lat_min"]) & (df["lat"]<=bbox["lat_max"])]
        pts_all = list(zip(df["lon"].tolist(), df["lat"].tolist()))
        if has_country:
            dfc = df[df["country"].astype(str).str.upper().isin(china_codes)]
            pts_china = list(zip(dfc["lon"].tolist(), dfc["lat"].tolist()))
            return pts_all, pts_china
        # 无 country 列则空间回退
        if BASE.china_poly is not None and not df.empty:
            g = gpd.GeoDataFrame(df.copy(), geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs="EPSG:4326")
            g["in_china"] = g.geometry.apply(lambda p: BASE.china_poly.contains(p))
            gc = g[g["in_china"]]
            pts_china = list(zip(gc["lon"].tolist(), gc["lat"].tolist()))
        return pts_all, pts_china

    # 无索引时退化：扫目录读首行
    ydir = find_year_dir(y)
    if not ydir:
        return [], []
    ll_all = []
    for fp in glob.glob(os.path.join(ydir, "*.csv")):
        try:
            # ISD 抽取得到的常见列名：LATITUDE / LONGITUDE 或 LAT / LON，做一点容错
            head = pd.read_csv(fp, nrows=1)
            if head.empty: 
                continue
            cols = {c.lower(): c for c in head.columns}
            lat_col = next((cols[k] for k in ["latitude","lat"] if k in cols), None)
            lon_col = next((cols[k] for k in ["longitude","lon"] if k in cols), None)
            if not lat_col or not lon_col:
                continue
            lat = float(head.iloc[0][lat_col]); lon = float(head.iloc[0][lon_col])
            if (bbox["lat_min"] <= lat <= bbox["lat_max"]) and (bbox["lon_min"] <= lon <= bbox["lon_max"]):
                ll_all.append((lon, lat))
        except Exception:
            continue
    # 退化路径下无法用国家码，尝试空间回退
    pts_all = ll_all
    pts_china = []
    if BASE.china_poly is not None and ll_all:
        for (x,y) in ll_all:
            if BASE.china_poly.contains(Point(x,y)):
                pts_china.append((x,y))
    return pts_all, pts_china

def parse_years(spec: str):
    s=set()
    for c in spec.split(","):
        c=c.strip()
        if "-" in c:
            a,b=c.split("-",1); s.update(range(int(a), int(b)+1))
        else:
            s.add(int(c))
    return sorted(y for y in s if 1900<=y<=2100)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", default="1929-2025", help="例如 1929-2025 或 1931,1954,1998")
    ap.add_argument("--bbox", nargs=4, type=float, default=None,
                    help="lon_min lon_max lat_min lat_max（默认与既有脚本一致）")
    ap.add_argument("--china-codes", default="CHN,CH,CN",
                    help="与索引country列匹配的中国国家码，逗号分隔；默认兼容 CHN/CH/CN")
    args = ap.parse_args()

    bbox = BBOX if args.bbox is None else dict(
        lon_min=args.bbox[0], lon_max=args.bbox[1], lat_min=args.bbox[2], lat_max=args.bbox[3]
    )
    years = parse_years(args.years)
    china_codes = {c.strip().upper() for c in args.china_codes.split(",") if c.strip()}

    # 预载底图
    ensure_dir(OUT_DIR)
    BASE.load()

    # 输出统计（与 GSOD 版文件名对应但前缀改为 isd）
    count_all_txt   = os.path.join(OUT_DIR, "yearly_counts_isd_bbox.txt")
    count_china_txt = os.path.join(OUT_DIR, "yearly_counts_isd_bbox_china.txt")
    fig_dir_all   = os.path.join(OUT_DIR, "maps_all")
    fig_dir_china = os.path.join(OUT_DIR, "maps_china")
    ensure_dir(fig_dir_all); ensure_dir(fig_dir_china)

    with open(count_all_txt, "w", encoding="utf-8") as fa, \
         open(count_china_txt, "w", encoding="utf-8") as fc:

        fa.write("# year  n_stations_bbox\n")
        fc.write("# year  n_stations_bbox_china\n")

        for y in years:
            pts_all, pts_ch = load_points_from_index(y, bbox, china_codes)
            fa.write(f"{y} {len(pts_all)}\n")
            fc.write(f"{y} {len(pts_ch)}\n")

            out_all   = os.path.join(fig_dir_all,   f"stations_{y}.png")
            out_china = os.path.join(fig_dir_china, f"stations_{y}_china.png")

            draw_map(y, pts_all, out_all, bbox, subtitle=f"BBOX stations (N={len(pts_all)})")
            draw_map(y, pts_ch,  out_china, bbox, subtitle=f"BBOX ∩ China (N={len(pts_ch)})")

            print(f"[map] {y}: bbox={len(pts_all)} -> {out_all} ; china={len(pts_ch)} -> {out_china}")

    print(f"[done] wrote counts: {count_all_txt} , {count_china_txt}")

if __name__ == "__main__":
    main()
