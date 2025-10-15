#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import math
import argparse
from collections import defaultdict, OrderedDict

import numpy as np
import geopandas as gpd
from shapely.geometry import Point
import matplotlib.pyplot as plt

# ========== 可配置区域（与现有脚本保持一致，可按需调整） ==========
BASE_DIR = os.path.expanduser("~/yangtze-1998-wrfhydro-rri/data/ghcnd")
SPLITS_DIR = os.path.join(BASE_DIR, "splits")
INVENTORY_PATH = os.path.join(BASE_DIR, "metadata", "ghcnd-inventory.txt")

OUT_DIR = os.path.expanduser("~/yangtze-1998-wrfhydro-rri/docs/figs")

# 研究窗口（示例；与单年脚本保持一致即可）
BBOX = dict(lon_min=85.5, lon_max=130.0, lat_min=18.0, lat_max=40.0)

SETUPS = OrderedDict({
    "outer_nest": (
        os.path.join(SPLITS_DIR, "stations_big_window"),
        "big_window"
    ),
    "outer_nest_china_only": (
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

# —— 绘图样式（与现有脚本风格一致）——
DPI = 300
LAND_FC = "#f0efe8"
LAND_EC = "#c6c3b6"
COUNTRY_EC = "#8b8b8b"
BASIN_EC = "#2a6f97"
MAIN_EC = "#153f65"
TRIB_EC = "#4f86c6"
STATION_FC = "#d04e4e"

COUNTRY_LW = 0.7
BASIN_LW = 1.4
MAIN_LW = 1.8
TRIB_LW = 1.2

# 子图中实际站点大小（地图上的点）
STATION_MS = 16
STATION_ALPHA = 0.9

# 面板年份与标签
PANEL_YEARS = [1931, 1935, 1954, 1998]
PANEL_TAGS = ["(a) 1931", "(b) 1935", "(c) 1954", "(d) 1998"]

# ========== 工具函数 ==========
def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

def in_bbox(lat: float, lon: float, bbox: dict) -> bool:
    return (bbox["lat_min"] <= lat <= bbox["lat_max"]) and (bbox["lon_min"] <= lon <= bbox["lon_max"])

def parse_inventory(inventory_path):
    out = []
    with open(inventory_path, "r", encoding="utf-8", errors="ignore") as fr:
        for line in fr:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 5:
                continue
            sid = parts[0]
            try:
                lat = float(parts[1]); lon = float(parts[2])
                elem = parts[3] if len(parts) >= 6 else "NA"
                y1 = int(parts[-2]); y2 = int(parts[-1])
                out.append((sid, lat, lon, elem, y1, y2))
            except Exception:
                continue
    return out

def read_station_set_from_folder(folder):
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

# ========== 底图加载 ==========
class BaseLayers:
    def __init__(self):
        self.land = None
        self.country = None
        self.basin = None
        self.main = None
        self.trib = None

    def load(self):
        if os.path.exists(NE_LAND_SHP):
            self.land = gpd.read_file(NE_LAND_SHP); self.land = self._to_wgs84(self.land)
        else:
            print(f"[warn] land shp not found: {NE_LAND_SHP}")

        if os.path.exists(NE_COUNTRY_SHP):
            self.country = gpd.read_file(NE_COUNTRY_SHP); self.country = self._to_wgs84(self.country)
        else:
            print(f"[warn] country shp not found: {NE_COUNTRY_SHP}")

        if YANGTZE_BASIN_UNION_SHP and os.path.exists(YANGTZE_BASIN_UNION_SHP):
            self.basin = gpd.read_file(YANGTZE_BASIN_UNION_SHP); self.basin = self._to_wgs84(self.basin)
        else:
            if YANGTZE_BASIN_UNION_SHP:
                print(f"[warn] basin shp not found: {YANGTZE_BASIN_UNION_SHP}")

        if YANGTZE_MAIN_GPKG and os.path.exists(YANGTZE_MAIN_GPKG):
            try:
                self.main = gpd.read_file(YANGTZE_MAIN_GPKG, layer=YANGTZE_MAIN_LAYER); self.main = self._to_wgs84(self.main)
            except Exception as e:
                print(f"[warn] load mainstem failed: {e}")
        else:
            if YANGTZE_MAIN_GPKG:
                print(f"[warn] mainstem gpkg not found: {YANGTZE_MAIN_GPKG}")

        if YANGTZE_TRIB_GPKG and os.path.exists(YANGTZE_TRIB_GPKG):
            try:
                self.trib = gpd.read_file(YANGTZE_TRIB_GPKG, layer=YANGTZE_TRIB_LAYER); self.trib = self._to_wgs84(self.trib)
            except Exception as e:
                print(f"[warn] load tribs failed: {e}")
        else:
            if YANGTZE_TRIB_GPKG:
                print(f"[warn] tribs gpkg not found: {YANGTZE_TRIB_GPKG}")

    @staticmethod
    def _to_wgs84(gdf):
        try:
            if gdf.crs is None:
                gdf.set_crs(epsg=4326, inplace=True)
            else:
                gdf = gdf.to_crs(epsg=4326)
        except Exception:
            pass
        return gdf

BASE = BaseLayers()

# ========== 坐标轴与刻度 ==========
def _nice_step(span):
    raw = span / 6.0
    candidates = [0.25, 0.5, 1, 2, 2.5, 5]
    step = min(candidates, key=lambda c: abs(c - raw))
    return step

def _setup_panel_axes(ax, bbox, show_left_labels, show_bottom_labels):
    ax.set_xlim(bbox["lon_min"], bbox["lon_max"])
    ax.set_ylim(bbox["lat_min"], bbox["lat_max"])
    # **保持等比例**（方案B）
    ax.set_aspect("equal", adjustable="box")

    lon_span = bbox["lon_max"] - bbox["lon_min"]
    lat_span = bbox["lat_max"] - bbox["lat_min"]
    lon_step = _nice_step(lon_span)
    lat_step = _nice_step(lat_span)

    ax.set_xticks(np.arange(math.ceil(bbox["lon_min"]), math.floor(bbox["lon_max"]) + 1e-6, lon_step))
    ax.set_yticks(np.arange(math.ceil(bbox["lat_min"]), math.floor(bbox["lat_max"]) + 1e-6, lat_step))

    # 四边都保留短刻度线，但只在左列/下排显示数字
    ax.tick_params(
        direction="inout", length=4, width=0.8, pad=2,
        bottom=True, top=True, left=True, right=True,
        labelbottom=show_bottom_labels, labelleft=show_left_labels,
        labeltop=False, labelright=False
    )

    # 四周边框
    for spine in ["left", "bottom", "right", "top"]:
        ax.spines[spine].set_visible(True)
        ax.spines[spine].set_color("black")
        ax.spines[spine].set_linewidth(0.8)

# ========== 底图与点 ==========
def _plot_baselayers(ax):
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

def _plot_points(ax, pts_lonlat):
    if not pts_lonlat:
        return
    gdf_pts = gpd.GeoDataFrame(geometry=[Point(x, y) for x, y in pts_lonlat], crs="EPSG:4326")
    gdf_pts.plot(ax=ax, marker="o", color=STATION_FC, markersize=STATION_MS, alpha=STATION_ALPHA, zorder=4)

# ========== 数据准备 ==========
def build_yearly_index(inventory, bbox, universe_ids):
    station_coord = {}
    yearly = defaultdict(set)
    for sid, lat, lon, elem, y1, y2 in inventory:
        if sid not in universe_ids:
            continue
        if not in_bbox(lat, lon, bbox):
            continue
        if sid not in station_coord:
            station_coord[sid] = (lon, lat)
        for y in range(y1, y2 + 1):
            yearly[y].add(sid)
    return station_coord, yearly

# ========== 主绘图：为一个 setup 画 2×2 比较图 ==========
def plot_comparison_for_setup(setup_name, setup_folder, out_subdir, inventory):
    print(f"[{setup_name}] building 2×2 comparison...")

    # 站点全集（以文件名为准）
    if not os.path.isdir(setup_folder):
        print(f"ERROR: folder not found: {setup_folder}", file=sys.stderr)
        return
    setup_ids = read_station_set_from_folder(setup_folder)
    if "china_only" in setup_name:
        setup_filter = lambda ids: {sid for sid in ids if sid[:2] in CHINA_CODES}
    else:
        setup_filter = lambda ids: ids

    # yearly 索引
    station_coord, yearly = build_yearly_index(inventory, BBOX, set(setup_ids))

    # 四年份点集
    panel_points = []
    for y in PANEL_YEARS:
        ids = setup_filter(yearly.get(y, set()) & setup_ids)
        pts = [station_coord[sid] for sid in ids if sid in station_coord]
        panel_points.append(pts)
        print(f"  year {y}: {len(pts)} stations")

    # ===== 关键：按 BBOX 自动算画布高宽与 hspace，使上下间距≈左右间距 =====
    lon_span = BBOX["lon_max"] - BBOX["lon_min"]
    lat_span = BBOX["lat_max"] - BBOX["lat_min"]
    ratio = lat_span / lon_span if lon_span > 0 else 1.0

    fig_width = 12.5                    # 你可以微调整体宽度
    k_fill = 1.00                       # 垂向填充系数（0.90–1.00 之间微调）
    fig_height = fig_width * ratio * k_fill

    wspace_val = 0.04                   # 基准左右间距（相对轴宽）
    # 垂直方向因高度更“紧”，用宽高比做修正；再乘 0.92 做人眼补偿
    hspace_val = wspace_val * (fig_width / fig_height) * 0.92

    fig, axes = plt.subplots(
        2, 2,
        figsize=(fig_width, fig_height),
        dpi=DPI,
        gridspec_kw=dict(wspace=wspace_val, hspace=hspace_val)
    )
    axes = axes.ravel()
    BASE.load()

    # 面板绘制
    for i, ax in enumerate(axes):
        show_left = (i % 2 == 0)        # 左列：i=0,2 → 显示纬度数字
        show_bottom = (i // 2 == 1)     # 下排：i=2,3 → 显示经度数字

        _plot_baselayers(ax)
        _plot_points(ax, panel_points[i])
        _setup_panel_axes(ax, BBOX, show_left, show_bottom)

        # 面板标签放图内左上角（不占外部空间）
        ax.text(0.02, 0.98, PANEL_TAGS[i],
                transform=ax.transAxes, ha="left", va="top", fontsize=11,
                bbox=dict(facecolor='white', edgecolor='none', alpha=0.55))

    # 单一图例（右侧外部，贴近主图）
    from matplotlib.lines import Line2D
    handles, labels = [], []
    handles.append(Line2D([], [], marker='o', color='none', markerfacecolor=STATION_FC, markersize=8))
    labels.append("GHCNd Station")
    if BASE.main is not None and not BASE.main.empty:
        handles.append(Line2D([], [], color=MAIN_EC, linewidth=MAIN_LW)); labels.append("Yangtze mainstem")
    if BASE.trib is not None and not BASE.trib.empty:
        handles.append(Line2D([], [], color=TRIB_EC, linewidth=TRIB_LW)); labels.append("Major tributaries")
    if BASE.basin is not None and not BASE.basin.empty:
        handles.append(Line2D([], [], color=BASIN_EC, linewidth=BASIN_LW)); labels.append("Yangtze basin boundary")

    fig.legend(
        handles, labels,
        loc="upper right",
        frameon=True, framealpha=0.9,
        fontsize=10, handlelength=1.6,
        labelspacing=0.4,
        facecolor="white"
    )

    # 全局坐标轴标签（更贴近图）
    fig.text(0.05, 0.5, "Latitude (°N)", va="center", ha="center",
             rotation="vertical", fontsize=12)
    fig.text(0.5, 0.03, "Longitude (°E)", va="center", ha="center",
             fontsize=12)

    # 收紧画布边距（右侧留出图例区）
    fig.subplots_adjust(
        left=0.085, right=0.96, bottom=0.075, top=0.94,
        wspace=wspace_val, hspace=hspace_val
    )

    # 总标题（含 setup 名）
    fig.suptitle(f"GHCNd Stations  |  setup: {setup_name}",
                 y=0.985, fontsize=13)

    # 输出
    out_dir = os.path.join(OUT_DIR, f"{out_subdir}_comparison")
    ensure_dir(out_dir)
    out_png = os.path.join(out_dir, f"{setup_name}_stations_comparison_2x2_equal.png")
    fig.savefig(out_png, bbox_inches="tight")
    plt.close(fig)
    print(f"[{setup_name}] wrote figure: {out_png}")

# ========== CLI ==========
def main():
    parser = argparse.ArgumentParser(description="Plot 2×2 comparison of stations for selected years per setup (equal-aspect, auto-spaced).")
    parser.add_argument("--setup", choices=list(SETUPS.keys()),
                        help="Only plot a single setup. If omitted, plot both.")
    args = parser.parse_args()

    # 读 inventory
    if not os.path.exists(INVENTORY_PATH):
        print(f"ERROR: inventory not found: {INVENTORY_PATH}", file=sys.stderr)
        sys.exit(1)
    inventory = parse_inventory(INVENTORY_PATH)

    # 跑一个或两个 setup
    if args.setup:
        folder, out_subdir = SETUPS[args.setup]
        plot_comparison_for_setup(args.setup, folder, out_subdir, inventory)
    else:
        for setup_name, (folder, out_subdir) in SETUPS.items():
            plot_comparison_for_setup(setup_name, folder, out_subdir, inventory)

    print("All done.")

if __name__ == "__main__":
    main()
