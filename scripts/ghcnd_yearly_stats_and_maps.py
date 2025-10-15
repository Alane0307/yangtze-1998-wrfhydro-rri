#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import math
from collections import defaultdict, OrderedDict
import glob

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import matplotlib.pyplot as plt

# ========== 可配置区域 ==========
BASE_DIR = os.path.expanduser("~/yangtze-1998-wrfhydro-rri/data/ghcnd")
SPLITS_DIR = os.path.join(BASE_DIR, "splits")
INVENTORY_PATH = os.path.join(BASE_DIR, "metadata", "ghcnd-inventory.txt")

OUT_DIR = os.path.expanduser("~/yangtze-1998-wrfhydro-rri/docs/figs")

# 研究窗口（需要更聚焦可改成 90–123E / 24–34.5N）
BBOX = dict(lon_min=85.5, lon_max=130.0, lat_min=18.0, lat_max=40.0)

SETUPS = OrderedDict({
    "big_window": (
        os.path.join(SPLITS_DIR, "stations_big_window"),
        "big_window"
    ),
    "big_window_china_only": (
        os.path.join(SPLITS_DIR, "stations_big_window_china_only"),
        "big_window_china_only"
    ),
})

CHINA_CODES = {"CH", "HK", "MC", "TW"}

# —— 叠加用地理图层（可留空则跳过该层）——
YANGTZE_BASIN_UNION_SHP = os.path.expanduser(
    "~/yangtze-1998-wrfhydro-rri/data/geodata/hydrobasins/yangtze_level5_union.shp"
)
YANGTZE_MAIN_GPKG = os.path.expanduser(
    "~/yangtze-1998-wrfhydro-rri/data/geodata/hydrorivers/yangtze_mainstem.gpkg"
)
YANGTZE_MAIN_LAYER = "yangtze_mainstem"
YANGTZE_TRIB_GPKG = os.path.expanduser(
    "~/yangtze-1998-wrfhydro-rri/data/geodata/hydrorivers/yangtze_major_tribs.gpkg"
)
YANGTZE_TRIB_LAYER = "yangtze_major_tribs"

# —— Natural Earth 底图（Shapefile）——
NE_LAND_SHP = os.path.expanduser(
    "~/yangtze-1998-wrfhydro-rri/data/geodata/natural_earth/ne_50m_land/ne_50m_land.shp"
)
NE_COUNTRY_SHP = os.path.expanduser(
    "~/yangtze-1998-wrfhydro-rri/data/geodata/natural_earth/ne_50m_admin_0_countries/ne_50m_admin_0_countries.shp"
)

# —— 绘图样式（可按需调整）——
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


# ========== 工具函数 ==========
def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def in_bbox(lat: float, lon: float, bbox: dict) -> bool:
    return (bbox["lat_min"] <= lat <= bbox["lat_max"]) and (bbox["lon_min"] <= lon <= bbox["lon_max"])


def parse_inventory(inventory_path):
    """
    解析 GHCND 的 ghcnd-inventory.txt
    标准格式（空白分隔）：ID LAT LON ELEMENT FIRSTYEAR LASTYEAR
    同一站点会有多行（不同 ELEMENT），我们按行返回，主流程会合并到 yearly 集合。
    返回迭代器： (sid, lat, lon, elem, first_year, last_year)
    """
    out = []
    with open(inventory_path, "r", encoding="utf-8", errors="ignore") as fr:
        for line in fr:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            # 容错：部分 inventory 可能有 5 或 6 列
            if len(parts) < 5:
                continue
            sid = parts[0]
            try:
                lat = float(parts[1])
                lon = float(parts[2])
                elem = parts[3] if len(parts) >= 6 else "NA"
                y1 = int(parts[-2])
                y2 = int(parts[-1])
                out.append((sid, lat, lon, elem, y1, y2))
            except Exception:
                # 忽略异常行
                continue
    return out


def read_station_set_from_folder(folder):
    """
    根据文件名收集站点 ID（不读内容）。
    例如：folder 内含 'CN000001.csv' 或 'CN000001.txt' 等，去除扩展名即为 ID。
    """
    ids = set()
    if not os.path.isdir(folder):
        return ids
    for p in os.listdir(folder):
        if p.startswith("."):
            continue
        sid = os.path.splitext(p)[0]
        if sid:
            ids.add(sid)
    return ids


# ========== 底图加载（全局缓存一次） ==========
class BaseLayers:
    def __init__(self):
        self.land = None
        self.country = None
        self.basin = None
        self.main = None
        self.trib = None

    def load(self):
        # Natural Earth
        if os.path.exists(NE_LAND_SHP):
            self.land = gpd.read_file(NE_LAND_SHP)
            self.land = self._to_wgs84(self.land)
        else:
            print(f"[warn] land shp not found: {NE_LAND_SHP}")

        if os.path.exists(NE_COUNTRY_SHP):
            self.country = gpd.read_file(NE_COUNTRY_SHP)
            self.country = self._to_wgs84(self.country)
        else:
            print(f"[warn] country shp not found: {NE_COUNTRY_SHP}")

        # 长江流域 union
        if YANGTZE_BASIN_UNION_SHP and os.path.exists(YANGTZE_BASIN_UNION_SHP):
            self.basin = gpd.read_file(YANGTZE_BASIN_UNION_SHP)
            self.basin = self._to_wgs84(self.basin)
        else:
            if YANGTZE_BASIN_UNION_SHP:
                print(f"[warn] basin shp not found: {YANGTZE_BASIN_UNION_SHP}")

        # 主要干流
        if YANGTZE_MAIN_GPKG and os.path.exists(YANGTZE_MAIN_GPKG):
            try:
                self.main = gpd.read_file(YANGTZE_MAIN_GPKG, layer=YANGTZE_MAIN_LAYER)
                self.main = self._to_wgs84(self.main)
            except Exception as e:
                print(f"[warn] load mainstem failed: {e}")
        else:
            if YANGTZE_MAIN_GPKG:
                print(f"[warn] mainstem gpkg not found: {YANGTZE_MAIN_GPKG}")

        # 主要支流
        if YANGTZE_TRIB_GPKG and os.path.exists(YANGTZE_TRIB_GPKG):
            try:
                self.trib = gpd.read_file(YANGTZE_TRIB_GPKG, layer=YANGTZE_TRIB_LAYER)
                self.trib = self._to_wgs84(self.trib)
            except Exception as e:
                print(f"[warn] load tribs failed: {e}")
        else:
            if YANGTZE_TRIB_GPKG:
                print(f"[warn] tribs gpkg not found: {YANGTZE_TRIB_GPKG}")

    @staticmethod
    def _to_wgs84(gdf):
        try:
            if gdf.crs is None:
                # 多数 Natural Earth/HydroBasins/HydroRIVERS 本身就是 WGS84
                # 若未标注 CRS，我们假定为 EPSG:4326
                gdf.set_crs(epsg=4326, inplace=True)
            else:
                gdf = gdf.to_crs(epsg=4326)
        except Exception:
            pass
        return gdf


BASE = BaseLayers()


# ========== 绘图 ==========
def _setup_axes(ax, bbox):
    ax.set_xlim(bbox["lon_min"], bbox["lon_max"])
    ax.set_ylim(bbox["lat_min"], bbox["lat_max"])
    ax.set_aspect("equal", adjustable="box")

    # 设定经纬度刻度（可根据窗口自动计算）
    lon_span = bbox["lon_max"] - bbox["lon_min"]
    lat_span = bbox["lat_max"] - bbox["lat_min"]
    lon_step = _nice_step(lon_span)
    lat_step = _nice_step(lat_span)
    ax.set_xticks(np.arange(math.ceil(bbox["lon_min"]), math.floor(bbox["lon_max"]) + 1e-6, lon_step))
    ax.set_yticks(np.arange(math.ceil(bbox["lat_min"]), math.floor(bbox["lat_max"]) + 1e-6, lat_step))
    ax.set_xlabel("Longitude (°E)")
    ax.set_ylabel("Latitude (°N)")


def _nice_step(span):
    # 简单选择：目标 ~5–7 个刻度
    raw = span / 6.0
    candidates = [0.25, 0.5, 1, 2, 2.5, 5]
    step = min(candidates, key=lambda c: abs(c - raw))
    return step


def draw_map(year, pts_lonlat, out_png, bbox):
    """
    pts_lonlat: [(lon, lat), ...]
    """
    ensure_dir(os.path.dirname(out_png))

    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)

    # 底图：陆地
    if BASE.land is not None and not BASE.land.empty:
        BASE.land.plot(ax=ax, facecolor=LAND_FC, edgecolor=LAND_EC, linewidth=0.4, zorder=0)

    # 底图：国界
    if BASE.country is not None and not BASE.country.empty:
        BASE.country.plot(ax=ax, facecolor="none", edgecolor=COUNTRY_EC, linewidth=COUNTRY_LW, zorder=1)

    # 长江流域边界
    if BASE.basin is not None and not BASE.basin.empty:
        BASE.basin.boundary.plot(ax=ax, color=BASIN_EC, linewidth=BASIN_LW, zorder=2)

    # 主要干流
    if BASE.main is not None and not BASE.main.empty:
        BASE.main.plot(ax=ax, color=MAIN_EC, linewidth=MAIN_LW, zorder=3)

    # 主要支流
    if BASE.trib is not None and not BASE.trib.empty:
        BASE.trib.plot(ax=ax, color=TRIB_EC, linewidth=TRIB_LW, zorder=3)

    # 站点
    if pts_lonlat:
        gdf_pts = gpd.GeoDataFrame(geometry=[Point(x, y) for x, y in pts_lonlat], crs="EPSG:4326")
        gdf_pts.plot(ax=ax, marker="o", color=STATION_FC, markersize=STATION_MS, alpha=STATION_ALPHA, zorder=4)

    _setup_axes(ax, bbox)
    ax.set_title(f"GHCNd Stations — {year}")

    # ===== 图例 =====
    handles = []
    labels = []

    from matplotlib.lines import Line2D

    if pts_lonlat:
        handles.append(Line2D([], [], marker='o', color='none',
                            markerfacecolor=STATION_FC, markersize=STATION_MS/1.6))
        labels.append("GHCNd Station")

    if BASE.main is not None and not BASE.main.empty:
        handles.append(Line2D([], [], color=MAIN_EC, linewidth=MAIN_LW))
        labels.append("Yangtze mainstem")

    if BASE.trib is not None and not BASE.trib.empty:
        handles.append(Line2D([], [], color=TRIB_EC, linewidth=TRIB_LW))
        labels.append("Major tributaries")

    if BASE.basin is not None and not BASE.basin.empty:
        handles.append(Line2D([], [], color=BASIN_EC, linewidth=BASIN_LW))
        labels.append("Yangtze basin boundary")

    ax.legend(handles, labels, loc="upper right", frameon=True, framealpha=0.9)

    plt.tight_layout()
    fig.savefig(out_png, bbox_inches="tight")
    plt.close(fig)


# ========== 测试图生成功能 ==========
def _test_generate_demo():
    """
    生成一张测试图，不依赖 inventory 和站点目录：
    - 在 BBOX 内生成几组示例点（含流域与河网叠加）
    """
    BASE.load()
    demo_pts = _synthetic_points(BBOX, n=60, seed=42)
    out_demo = os.path.join(OUT_DIR, "demo_test", "stations_demo_1998.png")
    draw_map(1998, demo_pts, out_demo, BBOX)
    print(f"[TEST] generated demo image: {out_demo}")


def _synthetic_points(bbox, n=50, seed=0):
    rng = np.random.default_rng(seed)
    lons = rng.uniform(bbox["lon_min"], bbox["lon_max"], n)
    lats = rng.uniform(bbox["lat_min"], bbox["lat_max"], n)
    return list(zip(lons, lats))


# ========== 主流程 ==========
def main():
    if "--test" in sys.argv:
        _test_generate_demo()
        return

    # 预加载底图（一次）
    BASE.load()

    # 1) 读 inventory
    if not os.path.exists(INVENTORY_PATH):
        print(f"ERROR: inventory not found: {INVENTORY_PATH}", file=sys.stderr)
        sys.exit(1)
    inv = parse_inventory(INVENTORY_PATH)

    # 2) 读两个 setup 的站点全集（以文件夹内文件名为准）
    setup_station_sets = {}
    for setup_name, (folder, _) in SETUPS.items():
        if not os.path.isdir(folder):
            print(f"ERROR: folder not found: {folder}", file=sys.stderr)
            sys.exit(1)
        setup_station_sets[setup_name] = read_station_set_from_folder(folder)
        print(f"[{setup_name}] station universe size = {len(setup_station_sets[setup_name])}")

    # 3) 仅处理两个 setup 并集中的站点
    universe = set().union(*setup_station_sets.values())
    station_coord = {}
    yearly_stations_any = defaultdict(set)

    min_year, max_year = 3000, -1
    for sid, lat, lon, elem, y1, y2 in inv:
        if sid not in universe:
            continue
        if not in_bbox(lat, lon, BBOX):
            continue
        if sid not in station_coord:
            station_coord[sid] = (lon, lat)
        # 使用元数据的起止年填充
        for y in range(y1, y2 + 1):
            yearly_stations_any[y].add(sid)
            if y < min_year: min_year = y
            if y > max_year: max_year = y

    if max_year < 0:
        print("No matching years found for the given station sets.", file=sys.stderr)
        sys.exit(1)

    # 限制到 1901–2025（若 metadata 更宽）
    min_year = max(1901, min_year)
    max_year = min(2025, max_year)

    # 4) 输出并画图
    ensure_dir(OUT_DIR)
    for setup_name, (folder, out_subdir) in SETUPS.items():
        out_txt = os.path.join(OUT_DIR, f"yearly_counts_{setup_name}.txt")
        fig_dir = os.path.join(OUT_DIR, out_subdir)
        ensure_dir(fig_dir)

        setup_ids = setup_station_sets[setup_name]
        with open(out_txt, "w", encoding="utf-8") as fw:
            fw.write("# year  n_stations\n")
            for y in range(min_year, max_year + 1):
                ids = yearly_stations_any.get(y, set()) & setup_ids
                if "china_only" in setup_name:
                    # GHCND 站号前两位为国家/地区码
                    ids = {sid for sid in ids if sid[:2] in CHINA_CODES}

                fw.write(f"{y} {len(ids)}\n")

                pts = [station_coord[sid] for sid in ids if sid in station_coord]
                out_png = os.path.join(fig_dir, f"stations_{y}.png")
                draw_map(y, pts, out_png, BBOX)

        print(f"[{setup_name}] wrote counts: {out_txt}")
        print(f"[{setup_name}] wrote maps to: {fig_dir}")

    print("All done.")


if __name__ == "__main__":
    main()
