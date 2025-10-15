#!/usr/bin/env python3
import os
import shutil

# 根路径
base_dir = os.path.expanduser("~/yangtze-1998-wrfhydro-rri/data/ghcnd/splits")

# 两个输入文件夹
folders = {
    "stations_big_window": "stations_big_window_china_only",
    "stations_yangtze_plus_buffer": "stations_yangzte_plus_buffer_china_only"
}

# 定义目标国家/地区代码
china_codes = {"CH", "HK", "MC", "TW"}

def filter_stations(src_folder, dst_folder):
    src_path = os.path.join(base_dir, src_folder)
    dst_path = os.path.join(base_dir, dst_folder)
    os.makedirs(dst_path, exist_ok=True)

    files = [f for f in os.listdir(src_path) if f.endswith(".csv")]
    kept = 0

    for f in files:
        # GHCN 站点ID的前两个字母为国家/地区代码
        country_code = f[:2]
        if country_code in china_codes:
            shutil.copy2(os.path.join(src_path, f), os.path.join(dst_path, f))
            kept += 1

    print(f"Folder '{src_folder}': kept {kept} Chinese/region stations")

def main():
    for src, dst in folders.items():
        filter_stations(src, dst)

if __name__ == "__main__":
    main()

