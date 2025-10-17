#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, sys, math, argparse, glob
from collections import OrderedDict
import numpy as np
import geopandas as gpd
from shapely.geometry import Point
import pandas as pd
import matplotlib.pyplot as plt

# ===== 路径与窗口设置（保持你原有输出路径不变） =====
GSOD_BASE = os.path.expanduser("~/yangtze-1998-wrfhydro-rri/data/gsod/extracted")
INDEX_DIR = os.path.expanduser("/data/gsod/index")
OUT_DIR   = os.path.expanduser("~/yangtze-1998-wrfhydro-rri/docs/figs/gsod_comparison")

# 外层嵌套窗口
BBOX = dict(lon_min=85.5, lon_max=130.0, lat_min=18.0, lat_max=40.0)

# —— 叠加用地理图层（路径改到 /data/geodata/）——
YANGTZE_BASIN_UNION_SHP = "/data/geodata/hydrobasins/yangtze_level5_union.shp"
YANGTZE_MAIN_GPKG = "/data/geodata/hydrorivers/yangtze_mainstem.gpkg"
YANGTZE_MAIN_LAYER = "yangtze_mainstem"
YANGTZE_TRIB_GPKG = "/data/geodata/hydrorivers/yangtze_major_tribs.gpkg"
YANGTZE_TRIB_LAYER = "yangtze_major_tribs"

# —— Natural Earth 底图 —— 
NE_LAND_SHP = "/data/geodata/natural_earth/ne_50m_land/ne_50m_land.shp"
NE_COUNTRY_SHP = "/data/geodata/natural_earth/ne_50m_admin_0_countries/ne_50m_admin_0_countries.shp"

# —— 绘图样式（与你原脚本一致）——
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

STATION_MS = 16
STATION_ALPHA = 0.9

# 面板年份与标签
PANEL_YEARS = [1931, 1935, 1954, 1998]
PANEL_TAGS  = ["(a) 1931", "(b) 1935", "(c) 1954", "(d) 1998"]

def ensure_dir(p): os.makedirs(p, exist_ok=True)

# ===== 底图缓存 =====
class BaseLayers:
    def __init__(self):
        self.land=self.country=self.basin=self.main=self.trib=None
        self.china_poly=None  # 供空间回退判断
    def load(self):
        if os.path.exists(NE_LAND_SHP):
            self.land = gpd.read_file(NE_LAND_SHP); self.land = self._to_wgs84(self.land)
        else:
            print(f"[warn] land shp not found: {NE_LAND_SHP}")
        if os.path.exists(NE_COUNTRY_SHP):
            self.country = gpd.read_file(NE_COUNTRY_SHP); self.country = self._to_wgs84(self.country)
            # 构造中国多边形（ADM0_A3=CHN 优先，其次 NAME/NAME_EN = China）
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
        if os.path.exists(YANGTZE_BASIN_UNION_SHP):
            self.basin = gpd.read_file(YANGTZE_BASIN_UNION_SHP); self.basin = self._to_wgs84(self.basin)
        if os.path.exists(YANGTZE_MAIN_GPKG):
            try:
                self.main = gpd.read_file(YANGTZE_MAIN_GPKG, layer=YANGTZE_MAIN_LAYER)
                self.main = self._to_wgs84(self.main)
            except Exception as e:
                print(f"[warn] load mainstem failed: {e}")
        if os.path.exists(YANGTZE_TRIB_GPKG):
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

# ===== 坐标轴策略 =====
def _nice_step(span):
    raw = span / 6.0
    candidates = [0.25, 0.5, 1, 2, 2.5, 5]
    return min(candidates, key=lambda c: abs(c - raw))

def _setup_panel_axes(ax, bbox, show_left_labels, show_bottom_labels):
    ax.set_xlim(bbox["lon_min"], bbox["lon_max"])
    ax.set_ylim(bbox["lat_min"], bbox["lat_max"])
    ax.set_aspect("equal", adjustable="box")
    lon_span = bbox["lon_max"] - bbox["lon_min"]
    lat_span = bbox["lat_max"] - bbox["lat_min"]
    ax.set_xticks(np.arange(math.ceil(bbox["lon_min"]), math.floor(bbox["lon_max"]) + 1e-6, _nice_step(lon_span)))
    ax.set_yticks(np.arange(math.ceil(bbox["lat_min"]), math.floor(bbox["lat_max"]) + 1e-6, _nice_step(lat_span)))
    ax.tick_params(direction="inout", length=4, width=0.8, pad=2,
                   bottom=True, top=True, left=True, right=True,
                   labelbottom=show_bottom_labels, labelleft=show_left_labels,
                   labeltop=False, labelright=False)
    for s in ["left","bottom","right","top"]:
        ax.spines[s].set_visible(True)
        ax.spines[s].set_color("black")
        ax.spines[s].set_linewidth(0.8)

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
    if not pts_lonlat: return
    gdf_pts = gpd.GeoDataFrame(geometry=[Point(x, y) for x, y in pts_lonlat], crs="EPSG:4326")
    gdf_pts.plot(ax=ax, marker="o", color=STATION_FC, markersize=STATION_MS, alpha=STATION_ALPHA, zorder=4)

# ===== 读取“全部”或“中国子集”的年站点 =====
def load_points_for_year(y: int, bbox: dict, china_only: bool, china_codes=("CHN","CH")):
    # 优先用索引（更快、可用country列）
    index_csv = os.path.join(INDEX_DIR, f"gsod_index_{y}.csv")
    pts = []
    if os.path.exists(index_csv):
        try:
            df = pd.read_csv(index_csv)
            # 先做 BBOX 约束
            df = df[(df["lon"]>=bbox["lon_min"]) & (df["lon"]<=bbox["lon_max"]) &
                    (df["lat"]>=bbox["lat_min"]) & (df["lat"]<=bbox["lat_max"])]
            if not china_only:
                return list(zip(df["lon"], df["lat"]))
            # 只取中国
            if "country" in df.columns:
                cc = {c.upper() for c in china_codes}
                dfc = df[df["country"].astype(str).str.upper().isin(cc)]
                return list(zip(dfc["lon"], dfc["lat"]))
            # 无 country 列 → 空间回退
            if BASE.china_poly is not None and not df.empty:
                g = gpd.GeoDataFrame(df.copy(), geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs="EPSG:4326")
                g["in_china"] = g.geometry.apply(lambda p: BASE.china_poly.contains(p))
                gc = g[g["in_china"]]
                return list(zip(gc["lon"], gc["lat"]))
            return []
        except Exception:
            pass

    # 无索引 → 扫该年目录读第一条记录拿经纬度
    year_dir = os.path.join(GSOD_BASE, str(y))
    if not os.path.isdir(year_dir):
        return []
    for fp in glob.glob(os.path.join(year_dir, "*.csv")):
        try:
            df = pd.read_csv(fp, header=0, nrows=1, usecols=["LATITUDE","LONGITUDE"])
            if df.empty: continue
            lat = float(df.iloc[0]["LATITUDE"]); lon = float(df.iloc[0]["LONGITUDE"])
            if bbox["lon_min"] <= lon <= bbox["lon_max"] and bbox["lat_min"] <= lat <= bbox["lat_max"]:
                if not china_only:
                    pts.append((lon, lat))
                else:
                    if BASE.china_poly is not None and BASE.china_poly.contains(Point(lon, lat)):
                        pts.append((lon, lat))
        except Exception:
            continue
    return pts

# ===== 面板绘制（复用一次生成两张：outer_nest / outer_nest_china_only） =====
def draw_panel(points_list, title_setup, out_png):
    # 依据 BBOX 计算画布尺寸与子图间距（沿用你原策略）
    lon_span = BBOX["lon_max"] - BBOX["lon_min"]
    lat_span = BBOX["lat_max"] - BBOX["lat_min"]
    ratio = lat_span / lon_span if lon_span > 0 else 1.0

    fig_width = 12.5
    k_fill = 1.00
    fig_height = fig_width * ratio * k_fill

    wspace_val = 0.04
    hspace_val = wspace_val * (fig_width / fig_height) * 0.92

    fig, axes = plt.subplots(
        2, 2,
        figsize=(fig_width, fig_height),
        dpi=DPI,
        gridspec_kw=dict(wspace=wspace_val, hspace=hspace_val)
    )
    axes = axes.ravel()

    # 逐面板绘制
    for i, ax in enumerate(axes):
        show_left   = (i % 2 == 0)
        show_bottom = (i // 2 == 1)
        _plot_baselayers(ax)
        _plot_points(ax, points_list[i])
        _setup_panel_axes(ax, BBOX, show_left, show_bottom)

        # 计算当前面板站点数量
        n_points = len(points_list[i])
        panel_label = f"{PANEL_TAGS[i]}   N={n_points}"

        ax.text(0.02, 0.98, panel_label,
                transform=ax.transAxes, ha="left", va="top", fontsize=11,
                bbox=dict(facecolor='white', edgecolor='none', alpha=0.55))

    # 统一图例
    from matplotlib.lines import Line2D
    handles, labels = [], []
    handles.append(Line2D([], [], marker='o', color='none', markerfacecolor=STATION_FC, markersize=8)); labels.append("GSOD Station")
    if BASE.main is not None and not BASE.main.empty:
        handles.append(Line2D([], [], color=MAIN_EC, linewidth=MAIN_LW)); labels.append("Yangtze mainstem")
    if BASE.trib is not None and not BASE.trib.empty:
        handles.append(Line2D([], [], color=TRIB_EC, linewidth=TRIB_LW)); labels.append("Major tributaries")
    if BASE.basin is not None and not BASE.basin.empty:
        handles.append(Line2D([], [], color=BASIN_EC, linewidth=BASIN_LW)); labels.append("Yangtze basin boundary")
    fig.legend(handles, labels, loc="upper right", frameon=True, framealpha=0.9, fontsize=10,
               handlelength=1.6, labelspacing=0.4, facecolor="white")

    # 轴标题
    fig.text(0.05, 0.5, "Latitude (°N)", va="center", ha="center", rotation="vertical", fontsize=12)
    fig.text(0.5, 0.03, "Longitude (°E)", va="center", ha="center", fontsize=12)

    # 总标题（不写 BBOX，用 setup 命名）
    fig.suptitle(f"GSOD Stations  |  setup: {title_setup}", y=0.985, fontsize=13)

    fig.subplots_adjust(left=0.085, right=0.96, bottom=0.075, top=0.94,
                        wspace=wspace_val, hspace=hspace_val)
    ensure_dir(os.path.dirname(out_png))
    fig.savefig(out_png, bbox_inches="tight")
    plt.close(fig)
    print(f"[done] wrote figure: {out_png}")

def main():
    parser = argparse.ArgumentParser(description="GSOD 2×2 yearly comparison (1931/1935/1954/1998)")
    parser.add_argument("--outdir", default=OUT_DIR, help="输出目录（默认仓库 docs/figs/gsod_comparison）")
    parser.add_argument("--china-codes", default="CHN,CH", help="country 列中国代码（逗号分隔）")
    args = parser.parse_args()

    ensure_dir(args.outdir)
    BASE.load()
    china_codes = tuple(c.strip().upper() for c in args.china_codes.split(",") if c.strip())

    # 组装两套点集：outer_nest / outer_nest_china_only
    points_all   = [load_points_for_year(y, BBOX, china_only=False, china_codes=china_codes) for y in PANEL_YEARS]
    points_china = [load_points_for_year(y, BBOX, china_only=True,  china_codes=china_codes) for y in PANEL_YEARS]

    # 输出两个文件（保持原名 + 再加一个 *_china.png）
    out_png_all   = os.path.join(args.outdir, "gsod_stations_comparison_2x2_equal.png")
    out_png_china = os.path.join(args.outdir, "gsod_stations_comparison_2x2_equal_china.png")

    draw_panel(points_all,   title_setup="outer_nest",               out_png=out_png_all)
    draw_panel(points_china, title_setup="outer_nest_china_only",    out_png=out_png_china)

if __name__ == "__main__":
    main()
