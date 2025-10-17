#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import math
import argparse
import re
from collections import defaultdict

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# ========== 可配置区域 ==========
# ISD 索引目录（对应 isd_build_index.py 的输出：/data/isd/index/isd_index_YYYY.csv）
ISD_INDEX_DIR = "/data/isd/index"

# 输出目录与 GSOD 版保持一致风格
OUT_DIR = os.path.expanduser("~/yangtze-1998-wrfhydro-rri/docs/figs")

# 研究窗口（决定“大窗口内”的判定）
BBOX = dict(lon_min=85.5, lon_max=130.0, lat_min=18.0, lat_max=40.0)

# 年份范围
YEAR_MIN, YEAR_MAX = 1901, 2025

# 需要高亮与加箭头的年份
HILIGHT_YEARS = [1931, 1935, 1954, 1998]

# ISD 索引的 country 列中，视为“中国”的代码集合（兼容港澳台）
CHINA_CODES_DEFAULT = {"CHN", "CH", "CN", "HK", "MC", "TW"}

# ========== 工具函数 ==========
def ensure_dir(p: str):
    os.makedirs(p, exist_ok=True)

def list_index_years(index_dir: str):
    """
    扫描 index 目录中的 isd_index_YYYY.csv，返回有序年份列表
    """
    index_dir = os.path.expanduser(index_dir)
    years = []
    if not os.path.isdir(index_dir):
        return years
    for name in os.listdir(index_dir):
        m = re.match(r"isd_index_(\d{4})\.csv$", name)
        if m:
            y = int(m.group(1))
            years.append(y)
    years = sorted([y for y in years if YEAR_MIN <= y <= YEAR_MAX])
    return years

def load_year_index(year: int):
    """
    读取某一年的 ISD 索引 CSV，返回 DataFrame（必须含 lon/lat；若有 country 列更好）
    """
    base = os.path.expanduser(ISD_INDEX_DIR)
    fp = os.path.join(base, f"isd_index_{year}.csv")
    if not os.path.exists(fp):
        return None
    try:
        df = pd.read_csv(fp)
        if not {"lon", "lat"}.issubset(df.columns):
            return None
        return df
    except Exception:
        return None

# ========== 统计逻辑（与 GSOD 版等价）==========
def build_yearly_active_sets_from_isd_index(bbox, china_codes):
    """
    基于 /data/isd/index/isd_index_YYYY.csv 构造：
      station_coord: {sid: (lon, lat)}
      yearly_active: {year: set(sid)}  —— 该年内“在 BBOX 内”的站点集合
      sid_is_china:  {sid: bool}       —— 站点是否属于中国（优先用 country 列判定）
    """
    station_coord = {}
    yearly_active = defaultdict(set)
    sid_is_china  = {}

    years = list_index_years(ISD_INDEX_DIR)
    for y in years:
        df = load_year_index(y)
        if df is None or df.empty:
            continue

        # 只统计 BBOX 内
        df = df[(df["lon"]>=bbox["lon_min"]) & (df["lon"]<=bbox["lon_max"]) &
                (df["lat"]>=bbox["lat_min"]) & (df["lat"]<=bbox["lat_max"])]

        if df.empty:
            continue

        # 站点ID列名：优先使用 station_id；若没有则以 lon/lat 拼装兜底
        sid_col = "station_id" if "station_id" in df.columns else None
        if sid_col is None:
            df["__sid__"] = df.apply(lambda r: f"{r['lon']:.5f}_{r['lat']:.5f}", axis=1)
            sid_col = "__sid__"

        # 国家列（用于中国判定）
        has_country = "country" in df.columns
        if has_country:
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

# ========== 绘图（逐年堆叠 + 高亮箭头，与 GSOD 版一致）==========
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

    # 与示例保持一致的配色（基础 + 高亮）
    col_out_base   = "#4575b4"
    col_china_base = "#c74b4b"
    col_out_hi     = "#2b5a99"
    col_china_hi   = "#a83f3f"

    out_colors   = [col_out_hi if y in HILIGHT_YEARS else col_out_base for y in years]
    china_colors = [col_china_hi if y in HILIGHT_YEARS else col_china_base for y in years]

    # 逐年堆叠（外部在下，中国在上）
    ax.bar(x, n_outside, width=width, color=out_colors, edgecolor="none",
           label="Outside China (within window)")
    ax.bar(x, n_china,   width=width, bottom=n_outside, color=china_colors, edgecolor="none",
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

    # 箭头指向该年总和顶端
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

# ========== 主流程 ==========
def main():
    parser = argparse.ArgumentParser(
        description="Plot yearly stacked bars of China vs non-China (within outer nest) for ISD, 1901–2025, with highlighted years.")
    parser.add_argument("--china-codes", default="CHN,CH,CN,HK,MC,TW",
                        help="Country codes that count as 'China' (comma-separated).")
    parser.add_argument("--outname", default="yearly_stations_china_vs_outside_highlight_isd.png",
                        help="Output PNG file name (under OUT_DIR).")
    args = parser.parse_args()

    china_codes = {c.strip().upper() for c in args.china_codes.split(",") if c.strip()}

    # 1) 从 ISD 索引构建 BBOX 内“逐年活跃站点”与“站点是否中国”的布尔表
    station_coord, yearly_active, sid_is_china = build_yearly_active_sets_from_isd_index(BBOX, china_codes)

    years_available = list_index_years(ISD_INDEX_DIR)
    if not years_available:
        print(f"[warn] No isd_index_YYYY.csv found in {ISD_INDEX_DIR} — proceeding with all-zero counts.")

    # 2) 始终画完整区间
    years = list(range(YEAR_MIN, YEAR_MAX + 1))
    for y in years:
        yearly_active.setdefault(y, set())

    # 3) 计算逐年序列（中国 vs 外部）
    n_cn, n_out = yearly_counts_by_region_from_index(years, yearly_active, sid_is_china, station_coord)

    # 4) 绘图（逐年版）
    out_png = os.path.join(OUT_DIR, args.outname)
    title = "ISD stations per year (1901–2025)\nChina vs outside-China within outer nest"
    plot_stacked_yearly_highlight(years, n_cn, n_out, out_png, title)

    # 5) 同步输出 CSV 便于复核
    csv_path = os.path.join(OUT_DIR, "yearly_stations_china_vs_outside_highlight_isd.csv")
    ensure_dir(OUT_DIR)
    with open(csv_path, "w", encoding="utf-8") as fw:
        fw.write("year,china,outside\n")
        for y, c1, c2 in zip(years, n_cn, n_out):
            fw.write(f"{y},{int(c1)},{int(c2)}\n")

    print(f"[done] wrote figure: {out_png}")
    print(f"[done] wrote csv:    {csv_path}")

if __name__ == "__main__":
    main()
