# -*- coding: utf-8 -*-
"""把发行目录打成 zip（UTF-8 文件名，跨机器解压不乱码）。

Python 的 zipfile 会对非 ASCII 文件名自动打上 UTF-8 标志（0x800），
而 bsdtar / 资源管理器自带压缩在这个环节都会退化成 GBK。

用法：
    python tools/make_zip.py 完整版 --exclude ""
    python tools/make_zip.py 精简版 --exclude models
"""
from __future__ import annotations

import argparse
import sys
import time
import zipfile
from pathlib import Path

SRC_ROOT = Path(r"E:\VoiceCloneStudio-Release\声纹工坊-v1.0.0")
OUT_DIR = Path(r"E:\VoiceCloneStudio-Release\dist")

# 已经是压缩格式的扩展名，直接存储不再压缩（省 30% 以上时间，体积几乎不变）
STORED_EXT = {".dll", ".pyd", ".exe", ".whl", ".zip", ".gz", ".safetensors",
              ".bin", ".pt", ".jpg", ".png", ".ico", ".mp3", ".wav"}


# 主包只放「程序」，不放这两类东西：
#   resources/gpt_sovits —— 可选扩展包，单独分发
#   resources/data       —— 用户数据（音色、生成音频、缓存、日志），私密且占体积
# 程序首次运行时 config.py 会自动重建 data 下的子目录
ALWAYS_EXCLUDE = ["resources/gpt_sovits", "resources/data"]


def collect(root: Path, exclude_dirs: list[str]) -> list[Path]:
    exclude = [str(root / e) for e in (ALWAYS_EXCLUDE + exclude_dirs) if e]
    out: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        sp = str(p)
        if any(sp.startswith(e) for e in exclude):
            continue
        out.append(p)
    return out


def build(tag: str, exclude_dirs: list[str]) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_zip = OUT_DIR / f"声纹工坊-v1.0.0-{tag}.zip"
    if out_zip.exists():
        out_zip.unlink()

    files = collect(SRC_ROOT, exclude_dirs)
    total = len(files)
    total_bytes = sum(f.stat().st_size for f in files)
    print(f"[{time.strftime('%H:%M:%S')}] {tag}: {total} 个文件 / "
          f"{total_bytes / 1024 ** 3:.2f} GB -> {out_zip.name}", flush=True)

    done_bytes = 0
    t0 = time.time()
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=1,
                         allowZip64=True) as z:
        for i, f in enumerate(files, 1):
            arc = Path(SRC_ROOT.name) / f.relative_to(SRC_ROOT)
            ext = f.suffix.lower()
            try:
                if ext in STORED_EXT:
                    z.write(f, arc, compress_type=zipfile.ZIP_STORED)
                else:
                    z.write(f, arc, compress_type=zipfile.ZIP_DEFLATED,
                            compresslevel=1)
            except (PermissionError, FileNotFoundError) as exc:
                print(f"  跳过 {arc}（{exc.__class__.__name__}）", flush=True)
            done_bytes += f.stat().st_size if f.exists() else 0
            if i % 2000 == 0 or i == total:
                pct = 100.0 * done_bytes / max(1, total_bytes)
                speed = done_bytes / max(1e-6, time.time() - t0) / 1024 ** 2
                print(f"  {i}/{total}  {pct:5.1f}%  {speed:5.1f} MB/s", flush=True)

    size = out_zip.stat().st_size
    ratio = size / max(1, total_bytes) * 100
    print(f"[{time.strftime('%H:%M:%S')}] 完成 {out_zip.name}  "
          f"{size / 1024 ** 3:.2f} GB（原 {total_bytes / 1024 ** 3:.2f} GB，"
          f"压缩率 {ratio:.0f}%），用时 {time.time() - t0:.0f}s", flush=True)
    return out_zip


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("--exclude", default="", help="models = 排除模型权重")
    args = ap.parse_args()

    excludes: list[str] = []
    if args.exclude == "models":
        excludes = ["resources/models/models--SWivid--F5-TTS",
                    "resources/models/models--charactr--vocos-mel-24khz"]

    if not SRC_ROOT.exists():
        raise SystemExit(f"找不到发行目录：{SRC_ROOT}")
    build(args.tag, excludes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
