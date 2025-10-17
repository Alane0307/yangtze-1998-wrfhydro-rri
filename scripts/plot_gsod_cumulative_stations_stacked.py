#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import math
import argparse
import re
from collections import defaultdict, OrderedDict

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# ========== 可配置区域 ==========
# GSOD 索引目录（之前我们生成的是 /data/gsod/index/gsod_index_YYYY.csv）
GSOD_INDEX_DIR = "/data/gsod/index"

# 输出目录保持与 GHCNd 版一致
OUT_DIR = os.path.expanduser("~/yangtze-1998-wrfhydro-rri/docs/figs")

# 研究窗口（决定“大窗口内”判定）
BBOX = dict(lon_min=85.5, lon_max=130.0, lat_min=18.0, lat_max=40.0)

# 年份范围（可按需调整）
YEAR_MIN, YEAR_MAX = 1901, 2025

# 需要高亮与加箭头的年份
HILIGHT_YEARS = [1931, 1935, 1954, 1998]

# GSOD 索引的国家列中，中国常见代码：优先 CH，其次 CN/CHN，并兼容港澳台
CHINA_CODES_DEFAULT = {"CH", "CN", "CHN", "HK", "MC", "TW"}

# ========== 工具函数 ==========
def ensure_dir(p: str):
    os.makedirs(p, exist_ok=True)

def in_bbox(lat: float, lon: float, bbox: dict) -> bool:
    return (bbox["lat_min"] <= lat <= bbox["lat_max"]) and (bbox["lon_min"] <= lon <= bbox["lon_max"])

def list_index_years(index_dir: str):
    """
    扫描 index 目录中的 gsod_index_YYYY.csv，返回有序年份列表
    """
    index_dir = os.path.expanduser(index_dir)     # ☆ 新增
    years = []
    if not os.path.isdir(index_dir):
        return years
    for name in os.listdir(index_dir):
        m = re.match(r"gsod_index_(\d{4})\.csv$", name)
        if m:
            y = int(m.group(1))
            years.append(y)
    years = sorted([y for y in years if YEAR_MIN <= y <= YEAR_MAX])
    return years

def load_year_index(year: int):
    """
    读取某一年的索引 CSV，返回 DataFrame（必须含 lon/lat；若有 country 列更好）
    """
    base = os.path.expanduser(GSOD_INDEX_DIR)     # ☆ 新增
    fp = os.path.join(GSOD_INDEX_DIR, f"gsod_index_{year}.csv")
    if not os.path.exists(fp):
        return None
    try:
        df = pd.read_csv(fp)
        # 必要列检查
        if not {"lon", "lat"}.issubset(df.columns):
            return None
        return df
    except Exception:
        return None

# ========== 统计逻辑 ==========
def build_yearly_active_sets_from_gsod_index(bbox, china_codes):
    """
    基于 /data/gsod/index/gsod_index_YYYY.csv 构造：
      station_coord: {sid: (lon, lat)}
      yearly_active: {year: set(sid)}  —— 该年内“在 BBOX 内”的站点集合
      sid_is_china:  {sid: bool}       —— 站点是否属于中国（优先用 country 列判定）
    """
    station_coord = {}
    yearly_active = defaultdict(set)
    sid_is_china  = {}

    years = list_index_years(GSOD_INDEX_DIR)
    for y in years:
        df = load_year_index(y)
        if df is None or df.empty:
            continue

        # 只统计 BBOX 内
        df = df[(df["lon"]>=bbox["lon_min"]) & (df["lon"]<=bbox["lon_max"]) &
                (df["lat"]>=bbox["lat_min"]) & (df["lat"]<=bbox["lat_max"])]

        if df.empty:
            continue

        # 站点ID列名适配
        sid_col = "station_id" if "station_id" in df.columns else None
        if sid_col is None:
            # 若没有 station_id，就把 lon/lat 组合成穷举 ID（极少见；只是兜底）
            df["__sid__"] = df.apply(lambda r: f"{r['lon']:.5f}_{r['lat']:.5f}", axis=1)
            sid_col = "__sid__"

        # 国家列（用于中国判定）
        has_country = "country" in df.columns
        if has_country:
            # 标准化为大写字符串
            df["country"] = df["country"].astype(str).str.upper()

        for _, row in df.iterrows():
            sid = str(row[sid_col])
            lon = float(row["lon"])
            lat = float(row["lat"])
            station_coord.setdefault(sid, (lon, lat))
            yearly_active[y].add(sid)

            if sid not in sid_is_china:
                if has_country:
                    sid_is_china[sid] = (row["country"] in china_codes)
                else:
                    # 没有国家列就标记为 False（不纳入中国累计）；如需空间判断可后续扩展
                    sid_is_china[sid] = False

    return station_coord, yearly_active, sid_is_china

def yearly_counts_by_region_from_index(years, yearly_active, sid_is_china, station_coord):
    """
    返回 n_china, n_outside —— 每一年当年（非累计）的站点数量
    """
    n_china = []
    n_outside = []
    for y in years:
        ids = yearly_active.get(y, set())
        cn = 0
        for sid in ids:
            if sid not in station_coord:
                continue
            cn += 1 if sid_is_china.get(sid, False) else 0
        out = max(0, len(ids) - cn)
        n_china.append(cn)
        n_outside.append(out)
    return np.array(n_china), np.array(n_outside)

def cumulative_counts_by_region_from_index(years, yearly_active, sid_is_china, station_coord):
    """
    返回 years, cum_china, cum_outside —— 站点累计（去重）
    """
    seen_china = set()
    seen_outside = set()

    cum_china = []
    cum_outside = []

    for y in years:
        ids = yearly_active.get(y, set())
        for sid in ids:
            if sid not in station_coord:
                continue
            if sid_is_china.get(sid, False):
                seen_china.add(sid)
            else:
                seen_outside.add(sid)
        cum_china.append(len(seen_china))
        cum_outside.append(len(seen_outside))

    return np.array(cum_china), np.array(cum_outside)

def plot_stacked_yearly_highlight(years, n_china, n_outside, out_png, title):
    ensure_dir(os.path.dirname(out_png))

    plt.rcParams.update({
        "font.size": 10,
        "axes.linewidth": 0.8,
        "xtick.direction": "inout",
        "ytick.direction": "inout",
        "xtick.major.size": 4,
        "ytick.major.size": 4
    })

    fig, ax = plt.subplots(figsize=(11.5, 5.6), dpi=300)

    x = np.array(years)
    width = 0.92

    # 与累计版一致的配色方案
    col_out_base   = "#4575b4"
    col_china_base = "#c74b4b"
    col_out_hi     = "#2b5a99"
    col_china_hi   = "#a83f3f"

    out_colors   = [col_out_hi if y in HILIGHT_YEARS else col_out_base for y in years]
    china_colors = [col_china_hi if y in HILIGHT_YEARS else col_china_base for y in years]

    # 逐年堆叠（外部在下，中国在上）
    bars_out = ax.bar(x, n_outside, width=width, color=out_colors, edgecolor="none",
                      label="Outside China (within window)")
    bars_cn  = ax.bar(x, n_china,   width=width, bottom=n_outside, color=china_colors, edgecolor="none",
                      label="China")

    ax.set_xlim(years[0] - 0.5, years[-1] + 0.5)
    ax.set_ylabel("Number of stations")  # 非累计
    ax.set_xlabel("Year")

    step = 10 if len(years) > 70 else 5
    xticks = list(range(years[0] - (years[0] % step) + step, years[-1] + 1, step))
    ax.set_xticks(xticks)

    ax.tick_params(bottom=True, top=True, left=True, right=True,
                   labelbottom=True, labelleft=True, labeltop=False, labelright=False, pad=2)

    for spine in ["left", "bottom", "right", "top"]:
        ax.spines[spine].set_visible(True)
        ax.spines[spine].set_color("black")
        ax.spines[spine].set_linewidth(0.8)

    from matplotlib.patches import Patch
    legend_handles = [
        Patch(facecolor=col_out_base,   edgecolor='none', label="Outside China (within window)"),
        Patch(facecolor=col_china_base, edgecolor='none', label="China")
    ]
    ax.legend(handles=legend_handles, loc="upper left", frameon=True, framealpha=0.9)
    ax.set_title(title)

    # 箭头依旧指向“该年总和”的顶端
    top_total = n_outside + n_china
    y_max = float(top_total.max())
    dy = max(10.0, 0.02 * y_max)

    for y in HILIGHT_YEARS:
        if y < years[0] or y > years[-1]:
            continue
        idx = y - years[0]
        x_pos = years[idx]
        y_pos = top_total[idx]
        ax.annotate(
            f"{y}",
            xy=(x_pos, y_pos), xycoords="data",
            xytext=(x_pos, y_pos + dy), textcoords="data",
            ha="center", va="bottom", fontsize=10,
            arrowprops=dict(arrowstyle="->", lw=0.9, shrinkA=0, shrinkB=0)
        )

    ax.set_ylim(0, y_max + 3 * dy)

    fig.tight_layout()
    fig.savefig(out_png, bbox_inches="tight")
    plt.close(fig)

# ========== 绘图（完全沿用 GHCNd 样式）==========
def plot_stacked_cumulative_highlight(years, cum_china, cum_outside, out_png, title):
    ensure_dir(os.path.dirname(out_png))

    # 科研绘图风格
    plt.rcParams.update({
        "font.size": 10,
        "axes.linewidth": 0.8,
        "xtick.direction": "inout",
        "ytick.direction": "inout",
        "xtick.major.size": 4,
        "ytick.major.size": 4
    })

    fig, ax = plt.subplots(figsize=(11.5, 5.6), dpi=300)

    x = np.array(years)
    width = 0.92

    # 颜色方案（常规 + 高亮）——与 GHCNd 版保持一致
    col_out_base   = "#4575b4"
    col_china_base = "#c74b4b"
    col_out_hi     = "#2b5a99"
    col_china_hi   = "#a83f3f"

    out_colors   = [col_out_hi if y in HILIGHT_YEARS else col_out_base for y in years]
    china_colors = [col_china_hi if y in HILIGHT_YEARS else col_china_base for y in years]

    bars_out = ax.bar(x, cum_outside, width=width, color=out_colors, edgecolor="none",
                      label="Outside China (within window, cumulative)")
    bars_cn  = ax.bar(x, cum_china,   width=width, bottom=cum_outside, color=china_colors, edgecolor="none",
                      label="China (cumulative)")

    ax.set_xlim(years[0] - 0.5, years[-1] + 0.5)
    ax.set_ylabel("Cumulative number of stations")
    ax.set_xlabel("Year")

    step = 10 if len(years) > 70 else 5
    xticks = list(range(years[0] - (years[0] % step) + step, years[-1] + 1, step))
    ax.set_xticks(xticks)

    ax.tick_params(bottom=True, top=True, left=True, right=True,
                   labelbottom=True, labelleft=True, labeltop=False, labelright=False, pad=2)

    for spine in ["left", "bottom", "right", "top"]:
        ax.spines[spine].set_visible(True)
        ax.spines[spine].set_color("black")
        ax.spines[spine].set_linewidth(0.8)

    from matplotlib.patches import Patch
    legend_handles = [
        Patch(facecolor=col_out_base,   edgecolor='none', label="Outside China (within window, cumulative)"),
        Patch(facecolor=col_china_base, edgecolor='none', label="China (cumulative)")
    ]
    ax.legend(handles=legend_handles, loc="upper left", frameon=True, framealpha=0.9)
    ax.set_title(title)

    top_total = cum_outside + cum_china
    y_max = float(top_total.max())
    dy = max(10.0, 0.02 * y_max)

    for y in HILIGHT_YEARS:
        if y < years[0] or y > years[-1]:
            continue
        idx = y - years[0]
        x_pos = years[idx]
        y_pos = top_total[idx]
        ax.annotate(
            f"{y}",
            xy=(x_pos, y_pos), xycoords="data",
            xytext=(x_pos, y_pos + dy), textcoords="data",
            ha="center", va="bottom", fontsize=10,
            arrowprops=dict(arrowstyle="->", lw=0.9, shrinkA=0, shrinkB=0)
        )

    ax.set_ylim(0, y_max + 3 * dy)

    fig.tight_layout()
    fig.savefig(out_png, bbox_inches="tight")
    plt.close(fig)

# ========== 主流程 ==========
def main():
    parser = argparse.ArgumentParser(
        description="Plot cumulative stacked bars of China vs non-China (within outer nest) for GSOD, 1901–2025, with highlighted years.")
    parser.add_argument("--china-codes", default="CH,CHN,CN,HK,MC,TW",
                        help="Country codes that count as 'China' in GSOD index (comma-separated). Default prefers 'CH'.")
    parser.add_argument("--outname", default="cumulative_stations_china_vs_outside_highlight_gsod.png",
                        help="Output PNG file name (under OUT_DIR).")
    args = parser.parse_args()

    china_codes = {c.strip().upper() for c in args.china_codes.split(",") if c.strip()}

    # 1) 从 GSOD 索引构建 BBOX 内的“逐年活跃站点”与“站点是否中国”的布尔表
    station_coord, yearly_active, sid_is_china = build_yearly_active_sets_from_gsod_index(BBOX, china_codes)

    years_available = list_index_years(GSOD_INDEX_DIR)

    # 2) 即便一个索引文件都没有，也不要退出，直接空集合（后面全部为 0）
    if not years_available:
        print(f"[warn] No gsod_index_YYYY.csv found in {GSOD_INDEX_DIR} — proceeding with all-zero counts.")
        years_available = []

    # 始终画完整区间
    years = list(range(YEAR_MIN, YEAR_MAX + 1))

    # 若 build_yearly_active_sets_from_gsod_index 只返回了部分年份，就补空集合
    for y in years:
        yearly_active.setdefault(y, set())

    # 3) 计算逐年序列（中国 vs 外部）
    n_cn, n_out = yearly_counts_by_region_from_index(years, yearly_active, sid_is_china, station_coord)

    # 4) 绘图（逐年版）
    out_png = os.path.join(OUT_DIR, "yearly_stations_china_vs_outside_highlight_gsod.png")
    title = "GSOD stations per year (1901–2025)\nChina vs outside-China within outer nest"
    plot_stacked_yearly_highlight(years, n_cn, n_out, out_png, title)

    # 5) 同步输出 CSV 便于复核
    csv_path = os.path.join(OUT_DIR, "yearly_stations_china_vs_outside_highlight_gsod.csv")
    ensure_dir(OUT_DIR)
    with open(csv_path, "w", encoding="utf-8") as fw:
        fw.write("year,china,outside\n")
        for y, c1, c2 in zip(years, n_cn, n_out):
            fw.write(f"{y},{int(c1)},{int(c2)}\n")

    print(f"[done] wrote figure: {out_png}")
    print(f"[done] wrote csv:    {csv_path}")

if __name__ == "__main__":
    main()
