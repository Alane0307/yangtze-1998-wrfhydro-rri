#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import math
import argparse
from collections import defaultdict, OrderedDict

import numpy as np
import matplotlib.pyplot as plt

# ========== 可配置区域 ==========
BASE_DIR = os.path.expanduser("~/yangtze-1998-wrfhydro-rri/data/ghcnd")
SPLITS_DIR = os.path.join(BASE_DIR, "splits")
INVENTORY_PATH = os.path.join(BASE_DIR, "metadata", "ghcnd-inventory.txt")

OUT_DIR = os.path.expanduser("~/yangtze-1998-wrfhydro-rri/docs/figs")

# 研究窗口（决定“大窗口内”判定）
BBOX = dict(lon_min=85.5, lon_max=130.0, lat_min=18.0, lat_max=40.0)

# 作为“大窗口”的站点全集，默认用 big_window 这个 setup
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

YEAR_MIN, YEAR_MAX = 1901, 2025  # 统计范围

# 需要高亮与加箭头的年份
HILIGHT_YEARS = [1931, 1935, 1954, 1998]

# ========== 工具函数 ==========
def ensure_dir(p: str):
    os.makedirs(p, exist_ok=True)

def in_bbox(lat: float, lon: float, bbox: dict) -> bool:
    return (bbox["lat_min"] <= lat <= bbox["lat_max"]) and (bbox["lon_min"] <= lon <= bbox["lon_max"])

def parse_inventory(inventory_path):
    """
    解析 ghcnd-inventory.txt
    返回列表：[(sid, lat, lon, elem, y1, y2), ...]
    """
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
    """
    根据文件名收集站点 ID（不读内容）。
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

# ========== 统计逻辑 ==========
def build_yearly_active_sets(inventory, bbox, universe_ids):
    """
    返回：
      station_coord: {sid: (lon, lat)}
      yearly_active: {year: set(sid)}  —— 该年内“有观测”的站点集合
    """
    station_coord = {}
    yearly_active = defaultdict(set)

    for sid, lat, lon, elem, y1, y2 in inventory:
        if sid not in universe_ids:
            continue
        if not in_bbox(lat, lon, bbox):
            continue
        if sid not in station_coord:
            station_coord[sid] = (lon, lat)
        y1c = max(YEAR_MIN, y1)
        y2c = min(YEAR_MAX, y2)
        if y2c < YEAR_MIN or y1c > YEAR_MAX:
            continue
        for y in range(y1c, y2c + 1):
            yearly_active[y].add(sid)

    return station_coord, yearly_active

def cumulative_counts_by_region(yearly_active, station_coord, china_codes):
    """
    基于 yearly_active 构造两个时间序列（累计）：
      - cum_china:   中国区域内的累计站点数（到当年为止的独立站点总数）
      - cum_outside: 在大窗口内但中国区域外的累计站点数
    """
    years = list(range(YEAR_MIN, YEAR_MAX + 1))
    seen_china = set()
    seen_outside = set()

    cum_china = []
    cum_outside = []

    for y in years:
        ids = yearly_active.get(y, set())
        for sid in ids:
            if sid in station_coord:
                if sid[:2] in china_codes:
                    seen_china.add(sid)
                else:
                    seen_outside.add(sid)
        cum_china.append(len(seen_china))
        cum_outside.append(len(seen_outside))

    return years, np.array(cum_china), np.array(cum_outside)

# ========== 绘图 ==========
def plot_stacked_cumulative_highlight(years, cum_china, cum_outside, out_png, title):
    """
    画累计堆叠柱状图（中国在上，外部在下），高亮特定年份并加箭头标注。
    """
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
    width = 0.92  # 略窄，避免完全贴合

    # 颜色方案（常规 + 高亮）
    col_out_base   = "#4575b4"
    col_china_base = "#c74b4b"
    col_out_hi     = "#2b5a99"  # 略深
    col_china_hi   = "#a83f3f"  # 略深

    # 为每个年份准备颜色数组（遇到高亮年份换色）
    out_colors   = [col_out_hi if y in HILIGHT_YEARS else col_out_base for y in years]
    china_colors = [col_china_hi if y in HILIGHT_YEARS else col_china_base for y in years]

    # 先画“外部（大窗口内非中国）”——在下方
    bars_out = ax.bar(x, cum_outside, width=width, color=out_colors, edgecolor="none", label="Outside China (within window, cumulative)")

    # 再画“中国”——堆在上方
    bars_cn = ax.bar(x, cum_china, width=width, bottom=cum_outside, color=china_colors, edgecolor="none", label="China (cumulative)")

    # 坐标轴 & 网格
    ax.set_xlim(years[0] - 0.5, years[-1] + 0.5)
    ax.set_ylabel("Cumulative number of stations")
    ax.set_xlabel("Year")

    # x 轴刻度（每 10 年）
    step = 10 if len(years) > 70 else 5
    xticks = list(range(years[0] - (years[0] % step) + step, years[-1] + 1, step))
    ax.set_xticks(xticks)

    # 只显示左/下坐标数字，但四边保留短刻度线
    ax.tick_params(bottom=True, top=True, left=True, right=True,
                   labelbottom=True, labelleft=True, labeltop=False, labelright=False, pad=2)

    # 边框
    for spine in ["left", "bottom", "right", "top"]:
        ax.spines[spine].set_visible(True)
        ax.spines[spine].set_color("black")
        ax.spines[spine].set_linewidth(0.8)

    # 图例与标题
    # 用“代理艺术家”确保图例颜色与标签稳定
    from matplotlib.patches import Patch
    legend_handles = [
        Patch(facecolor=col_out_base,   edgecolor='none', label="Outside China (within window, cumulative)"),
        Patch(facecolor=col_china_base, edgecolor='none', label="China (cumulative)")
    ]
    ax.legend(handles=legend_handles, loc="upper left", frameon=True, framealpha=0.9)
    ax.set_title(title)

    # ---- 高亮年份的箭头标注 ----
    top_total = cum_outside + cum_china
    y_max = float(top_total.max())
    # 箭头和文字的相对偏移
    dy = max(10.0, 0.02 * y_max)  # 文字与箭头头部上方的距离
    for y in HILIGHT_YEARS:
        if y < years[0] or y > years[-1]:
            continue
        idx = y - years[0]
        x_pos = years[idx]
        y_pos = top_total[idx]

        # 注解文字：稍向上偏移
        ax.annotate(
            f"{y}",
            xy=(x_pos, y_pos), xycoords="data",
            xytext=(x_pos, y_pos + dy), textcoords="data",
            ha="center", va="bottom", fontsize=10,
            arrowprops=dict(arrowstyle="->", lw=0.9, shrinkA=0, shrinkB=0)
        )

    # 顶部留白，避免箭头文字贴边
    ax.set_ylim(0, y_max + 3 * dy)

    fig.tight_layout()
    fig.savefig(out_png, bbox_inches="tight")
    plt.close(fig)

# ========== 主流程 ==========
def main():
    parser = argparse.ArgumentParser(description="Plot cumulative stacked bars of China vs non-China (within big window) stations, 1901–2025, with highlighted years.")
    parser.add_argument("--setup", default="big_window", choices=list(SETUPS.keys()),
                        help="Which setup folder defines the big-window universe (default: big_window).")
    parser.add_argument("--outname", default="cumulative_stations_china_vs_outside_highlight.png",
                        help="Output PNG file name (under OUT_DIR).")
    args = parser.parse_args()

    # 1) 读 inventory
    if not os.path.exists(INVENTORY_PATH):
        print(f"ERROR: inventory not found: {INVENTORY_PATH}", file=sys.stderr)
        sys.exit(1)
    inv = parse_inventory(INVENTORY_PATH)

    # 2) 读 setup 站点全集（作为“大窗口内”的 universe）
    setup_folder, out_subdir = SETUPS[args.setup]
    if not os.path.isdir(setup_folder):
        print(f"ERROR: folder not found: {setup_folder}", file=sys.stderr)
        sys.exit(1)
    universe_ids = read_station_set_from_folder(setup_folder)
    print(f"[{args.setup}] universe size = {len(universe_ids)}")

    # 3) 基于 BBOX + universe 构建“每年活跃站点集合”
    station_coord, yearly_active = build_yearly_active_sets(inv, BBOX, universe_ids)

    # 4) 构造累计时间序列（中国 vs 大窗口内非中国）
    years, cum_cn, cum_out = cumulative_counts_by_region(yearly_active, station_coord, CHINA_CODES)

    # 5) 绘图（中国在上，外部在下；高亮四年份并加箭头）
    out_png = os.path.join(OUT_DIR, args.outname)
    title = "GHCNd stations cumulative counts (1901–2025)\nChina vs outside-China within outer nest"
    plot_stacked_cumulative_highlight(years, cum_cn, cum_out, out_png, title)

    # 6) 同时输出 CSV 便于复核
    csv_path = os.path.join(OUT_DIR, "cumulative_stations_china_vs_outside_highlight.csv")
    ensure_dir(OUT_DIR)
    with open(csv_path, "w", encoding="utf-8") as fw:
        fw.write("year,cum_china,cum_outside\n")
        for y, c1, c2 in zip(years, cum_cn, cum_out):
            fw.write(f"{y},{int(c1)},{int(c2)}\n")

    print(f"[done] wrote figure: {out_png}")
    print(f"[done] wrote csv:    {csv_path}")

if __name__ == "__main__":
    main()
