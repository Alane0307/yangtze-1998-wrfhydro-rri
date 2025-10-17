#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import sys
import math
from collections import defaultdict, OrderedDict

import numpy as np
import geopandas as gpd
from shapely.geometry import Point
import matplotlib.pyplot as plt

# ========= 可配置区域（与 ghcnd 脚本保持一致的风格与底图） =========
BASE_DIR = os.path.expanduser("~/yangtze-1998-wrfhydro-rri/data/isd")
META_DIR = os.path.join(BASE_DIR, "metadata")
HISTORY_PATH = os.path.join(META_DIR, "isd-history.txt")
INVENTORY_PATH = os.path.join(META_DIR, "isd-inventory.txt")

OUT_DIR = os.path.expanduser("~/yangtze-1998-wrfhydro-rri/docs/figs")

# 研究窗口（与 ghcnd 同款）
BBOX = dict(lon_min=85.5, lon_max=130.0, lat_min=18.0, lat_max=40.0)
CHINA_CODES = {"CH", "HK", "MC", "TW", "CN"}  # ISD 历史表 CTRY=FIPS / WMO，常见为"CH"；冗余包含 CN 等

# 两个输出 setup：大窗口全部站点；仅中国站点（国家码判定）
SETUPS = OrderedDict({
    "isd_big_window": dict(filter_fn=lambda rec: in_bbox(rec["lat"], rec["lon"], BBOX)),
    "isd_big_window_china_only": dict(filter_fn=lambda rec: in_bbox(rec["lat"], rec["lon"], BBOX) and (rec.get("ctry") in CHINA_CODES)),
})

# —— 叠加用地理图层（路径与 ghcnd 保持一致）——
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

# —— 绘图样式（与 ghcnd 同款）——
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

MIN_YEAR, MAX_YEAR = 1901, 2025  # 与数据档期对齐


# ========= 工具 =========
def ensure_dir(p):
    os.makedirs(p, exist_ok=True)

def in_bbox(lat, lon, bbox):
    return (bbox["lat_min"] <= lat <= bbox["lat_max"]) and (bbox["lon_min"] <= lon <= bbox["lon_max"])

def _nice_step(span):
    raw = span / 6.0  # 目标 ~5–7 tick
    candidates = [0.25, 0.5, 1, 2, 2.5, 5]
    return min(candidates, key=lambda c: abs(c - raw))

# ========= 读 isd-history（取坐标/国家/起止日期） =========
def parse_isd_history(path):
    """
    返回 dict:
      sid -> { 'lat': float, 'lon': float, 'ctry': str, 'begin': int(YYYYMMDD), 'end': int(YYYYMMDD) }
    行示例与列含义见文件头（USAF, WBAN, CTRY, LAT, LON, BEGIN, END 等）。
    """
    sid2meta = {}
    # 允许 header/空行，允许缺失字段（用正则宽松抽取）
    pat = re.compile(
        r'^\s*(?P<usaf>\S+)\s+(?P<wban>\S+)\s+(?P<rest>.*)$'
    )

    # 尝试从尾部字段抽取经纬度/高程/起止日期
    tail_pat = re.compile(
        r'(?P<lat>[+-]?\d+(?:\.\d+)?)\s+(?P<lon>[+-]?\d+(?:\.\d+)?)\s+(?P<elev>[+-]?\d+(?:\.\d+)?)?\s+(?P<begin>\d{8})\s+(?P<end>\d{8})\s*$'
    )

    with open(path, "r", encoding="utf-8", errors="ignore") as fr:
        for line in fr:
            if not line.strip():
                continue
            if line.lstrip().startswith(("*", "USAF", "Integrated", "Notes:", "CTRY", "WBAN")):
                # 跳过说明/标题
                continue
            m = pat.match(line)
            if not m:
                continue
            usaf = m.group("usaf")
            wban = m.group("wban")
            rest = m.group("rest")

            # 国家码通常在“站名  CTRY ST CALL LAT LON ELEV BEGIN END”的 CTRY 列
            # 为简单起见，从 rest 中尽量抓取 CTRY 的两位/两到三位大写字符串（在经纬度之前）
            # 先用尾部经纬度/日期定位，再在其之前找 CTRY
            m2 = tail_pat.search(rest)
            if not m2:
                continue
            lat = float(m2.group("lat"))
            lon = float(m2.group("lon"))
            begin = int(m2.group("begin"))
            end = int(m2.group("end"))

            head = rest[:m2.start()].rstrip()
            # CTRY 通常靠近尾部，尝试在 head 末端找两到三位大写字母
            m_ctry = re.search(r'([A-Z]{2,3})\s*$', head)
            ctry = m_ctry.group(1) if m_ctry else ""

            sid = f"{usaf}-{wban}"
            sid2meta[sid] = dict(lat=lat, lon=lon, ctry=ctry, begin=begin, end=end)
    return sid2meta

# ========= 读 isd-inventory（判断每年活跃） =========
def parse_isd_inventory(path):
    """
    返回:
      yearly_active: dict[year] -> set(sid)
    定义：某站-年的 12 个月份计数求和 >0 则该年“活跃”。
    """
    yearly_active = defaultdict(set)
    with open(path, "r", encoding="utf-8", errors="ignore") as fr:
        for line in fr:
            line = line.strip()
            if not line or line.startswith(("*", "USAF")):
                continue
            parts = line.split()
            if len(parts) < 15:
                continue
            usaf, wban, y = parts[0], parts[1], parts[2]
            try:
                year = int(y)
            except ValueError:
                continue
            # 剩下 12 列是每月计数
            try:
                months = [int(v) for v in parts[3:3+12]]
            except Exception:
                continue
            if sum(months) > 0:
                sid = f"{usaf}-{wban}"
                yearly_active[year].add(sid)
    return yearly_active

# ========= 底图缓存 =========
class BaseLayers:
    def __init__(self):
        self.land = None
        self.country = None
        self.basin = None
        self.main = None
        self.trib = None

    def load(self):
        if os.path.exists(NE_LAND_SHP):
            self.land = gpd.read_file(NE_LAND_SHP)
            self.land = self._to_wgs84(self.land)
        if os.path.exists(NE_COUNTRY_SHP):
            self.country = gpd.read_file(NE_COUNTRY_SHP)
            self.country = self._to_wgs84(self.country)
        if YANGTZE_BASIN_UNION_SHP and os.path.exists(YANGTZE_BASIN_UNION_SHP):
            self.basin = gpd.read_file(YANGTZE_BASIN_UNION_SHP)
            self.basin = self._to_wgs84(self.basin)
        if YANGTZE_MAIN_GPKG and os.path.exists(YANGTZE_MAIN_GPKG):
            try:
                self.main = gpd.read_file(YANGTZE_MAIN_GPKG, layer=YANGTZE_MAIN_LAYER)
                self.main = self._to_wgs84(self.main)
            except Exception:
                pass
        if YANGTZE_TRIB_GPKG and os.path.exists(YANGTZE_TRIB_GPKG):
            try:
                self.trib = gpd.read_file(YANGTZE_TRIB_GPKG, layer=YANGTZE_TRIB_LAYER)
                self.trib = self._to_wgs84(self.trib)
            except Exception:
                pass

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

# ========= 画图 =========
def _setup_axes(ax, bbox):
    ax.set_xlim(bbox["lon_min"], bbox["lon_max"])
    ax.set_ylim(bbox["lat_min"], bbox["lat_max"])
    ax.set_aspect("equal", adjustable="box")
    lon_span = bbox["lon_max"] - bbox["lon_min"]
    lat_span = bbox["lat_max"] - bbox["lat_min"]
    ax.set_xticks(np.arange(math.ceil(bbox["lon_min"]), math.floor(bbox["lon_max"]) + 1e-6, _nice_step(lon_span)))
    ax.set_yticks(np.arange(math.ceil(bbox["lat_min"]), math.floor(bbox["lat_max"]) + 1e-6, _nice_step(lat_span)))
    ax.set_xlabel("Longitude (°E)")
    ax.set_ylabel("Latitude (°N)")

def draw_map(year, pts_lonlat, out_png, bbox, setup_label="ISD Station"):
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
        gpd.GeoDataFrame(geometry=[Point(x, y) for x, y in pts_lonlat], crs="EPSG:4326") \
            .plot(ax=ax, marker="o", color=STATION_FC, markersize=STATION_MS, alpha=STATION_ALPHA, zorder=4)

    _setup_axes(ax, bbox)
    ax.set_title(f"ISD Stations — {year}")

    from matplotlib.lines import Line2D
    handles = []
    labels = []
    if pts_lonlat:
        handles.append(Line2D([], [], marker='o', color='none', markerfacecolor=STATION_FC, markersize=STATION_MS/1.6))
        labels.append(setup_label)
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

# ========= 主流程 =========
def main():
    # 预加载底图
    BASE.load()

    if not os.path.exists(HISTORY_PATH):
        print(f"ERROR: isd-history not found: {HISTORY_PATH}", file=sys.stderr); sys.exit(1)
    if not os.path.exists(INVENTORY_PATH):
        print(f"ERROR: isd-inventory not found: {INVENTORY_PATH}", file=sys.stderr); sys.exit(1)

    # 1) 读元数据与活跃年
    sid2meta = parse_isd_history(HISTORY_PATH)
    yearly_active = parse_isd_inventory(INVENTORY_PATH)

    # 2) 生成两个 setup 的统计与地图
    ensure_dir(OUT_DIR)
    min_y, max_y = MIN_YEAR, MAX_YEAR

    for setup_name, cfg in SETUPS.items():
        filter_fn = cfg["filter_fn"]
        # 先筛出满足条件的 station universe
        universe = {sid for sid, rec in sid2meta.items() if filter_fn(rec)}
        # 输出计数文件
        out_txt = os.path.join(OUT_DIR, f"yearly_counts_{setup_name}.txt")
        fig_dir = os.path.join(OUT_DIR, setup_name)
        ensure_dir(fig_dir)

        with open(out_txt, "w", encoding="utf-8") as fw:
            fw.write("# year  n_stations\n")
            for y in range(min_y, max_y + 1):
                ids = yearly_active.get(y, set()) & universe
                fw.write(f"{y} {len(ids)}\n")
                pts = [(sid2meta[s]["lon"], sid2meta[s]["lat"]) for s in ids if s in sid2meta]
                out_png = os.path.join(fig_dir, f"stations_{y}.png")
                draw_map(y, pts, out_png, BBOX, setup_label="ISD Station")

        print(f"[{setup_name}] wrote counts: {out_txt}")
        print(f"[{setup_name}] wrote maps to: {fig_dir}")

    print("All done.")

if __name__ == "__main__":
    main()
