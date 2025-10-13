#!/usr/bin/env python3
import os, sys, tarfile, time, stat

BASE = os.path.expanduser("~/yangtze-1998-wrfhydro-rri/data/gsod")
RAW_DIR = os.path.join(BASE, "raw")
OUT_DIR = os.path.join(BASE, "extracted")
LOG_DIR = os.path.join(BASE, "reports")
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

LOG = os.path.join(LOG_DIR, f"extract_gsod_{time.strftime('%Y%m%d_%H%M')}.log")

def is_safe_path(basedir, path):
    # 防止目录穿越（/绝对路径、.. 回退）
    return os.path.realpath(path).startswith(os.path.realpath(basedir) + os.sep)

def safe_extract(tar: tarfile.TarFile, out_dir: str):
    count = 0
    skipped = 0
    for m in tar:
        # 仅处理普通文件和目录
        if not (m.isdir() or m.isreg()):
            continue

        # 计算输出路径：保持 tar 内部的相对层级
        target = os.path.join(out_dir, m.name.lstrip("/"))

        # 路径安全检查
        if not is_safe_path(out_dir, target):
            print(f"[WARN] Skip unsafe path: {m.name}", file=sys.stderr)
            continue

        # 目录则确保存在
        if m.isdir():
            os.makedirs(target, exist_ok=True)
            continue

        # 文件：若已存在且大小一致，跳过（断点/可重入）
        if os.path.exists(target) and os.path.getsize(target) == m.size:
            skipped += 1
            continue

        # 确保父目录
        os.makedirs(os.path.dirname(target), exist_ok=True)

        # 解压该成员（流式，避免内存爆）
        with tar.extractfile(m) as src, open(target, "wb") as dst:
            if src is None:
                print(f"[WARN] Null member: {m.name}", file=sys.stderr)
                continue
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                dst.write(chunk)

        # 复制权限位（可选）
        try:
            os.chmod(target, m.mode & 0o777)
        except Exception:
            pass

        count += 1
        if count % 500 == 0:
            print(f"[INFO] extracted {count} files …")

    return count, skipped

def main():
    # 可传入年份范围：python extract_gsod_safely.py 1980 2025
    start, end = None, None
    if len(sys.argv) == 3:
        start, end = int(sys.argv[1]), int(sys.argv[2])

    tgzs = sorted([f for f in os.listdir(RAW_DIR) if f.endswith(".tar.gz")])
    if start and end:
        tgzs = [f for f in tgzs if f[:4].isdigit() and start <= int(f[:4]) <= end]

    if not tgzs:
        print("No .tar.gz found in", RAW_DIR)
        return

    with open(LOG, "w") as log:
        for f in tgzs:
            year = f[:4] if f[:4].isdigit() else "unknown"
            tar_path = os.path.join(RAW_DIR, f)
            out_dir = os.path.join(OUT_DIR, year)
            os.makedirs(out_dir, exist_ok=True)

            msg = f"[START] {f} -> {out_dir}"
            print(msg); log.write(msg + "\n"); log.flush()

            try:
                # 只读 gzip（流式，避免一次性展开）
                with tarfile.open(tar_path, mode="r:gz") as tar:
                    extracted, skipped = safe_extract(tar, out_dir)
                msg = f"[DONE]  {f}: extracted={extracted}, skipped={skipped}"
                print(msg); log.write(msg + "\n"); log.flush()
            except Exception as e:
                msg = f"[FAIL]  {f}: {e}"
                print(msg); log.write(msg + "\n"); log.flush()

    print(f"[LOG] details -> {LOG}")

if __name__ == "__main__":
    main()

