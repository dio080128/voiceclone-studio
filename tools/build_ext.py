# -*- coding: utf-8 -*-
"""构建「多语言扩展包」（GPT-SoVITS 独立运行时）。

主程序（Python 3.13）装不下 GPT-SoVITS 的依赖，所以它跑在一套独立的
Python 3.10 里。扩展包就是把那套运行时 + 代码 + 模型打成一个 zip，
用户解压到 resources/ 下（得到 resources/gpt_sovits/）即可启用。

用法：
    python tools/build_ext.py            # 构建目录 + zip
    python tools/build_ext.py --no-zip   # 只构建目录
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

SRC_RUNTIME = Path(r"E:\Python310")          # Python 3.10 + site-packages
SRC_GS = Path(r"E:\Python310\gs")            # GPT-SoVITS 代码 + pretrained_models
DIST = Path(r"E:\VoiceCloneStudio-Release\dist")
PKG_NAME = "声纹工坊-v1.0.0-多语言扩展包"
EXT_NAME = "gpt_sovits"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def robocopy(src: Path, dst: Path, exclude_dirs: list[Path]) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    cmd = ["robocopy", str(src), str(dst), "/E", "/MT:8", "/NFL", "/NDL",
           "/NJH", "/NJS", "/NP", "/R:1", "/W:1", "/XF", "*.pyc"]
    if exclude_dirs:
        cmd += ["/XD"] + [str(d) for d in exclude_dirs]
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    # robocopy：0-7 都是正常（8+ 才代表出错）
    if r.returncode >= 8:
        raise RuntimeError(f"robocopy 失败({r.returncode}): {r.stdout[-800:]}")


def build_dir() -> Path:
    out_root = DIST / PKG_NAME
    ext = out_root / EXT_NAME
    log(f"输出目录 {out_root}")
    if out_root.exists():
        log("清理旧目录…")
        shutil.rmtree(out_root, ignore_errors=True)
    out_root.mkdir(parents=True, exist_ok=True)

    log("复制 Python 3.10 运行时（约 1.5 GB）…")
    robocopy(SRC_RUNTIME, ext / "python", [SRC_RUNTIME / "gs"])

    log("复制 GPT-SoVITS 代码与模型（约 1.2 GB）…")
    robocopy(SRC_GS, ext, [SRC_GS / ".git", SRC_GS / "__pycache__"])

    # 运行时要能直接跑起来：_pth 已指向 Lib\site-packages，这里只做校验
    py = ext / "python" / "python.exe"
    if not py.exists():
        raise RuntimeError("复制后找不到 python.exe")
    for must in ("api_v2.py", "launch_api.py",
                 "GPT_SoVITS/pretrained_models/gsv-v2final-pretrained/s2G2333k.pth"):
        if not (ext / must.replace("/", "\\")).exists():
            raise RuntimeError(f"缺少关键文件：{must}")

    (out_root / "安装说明.txt").write_text(
        "\n".join([
            "声纹工坊 · 多语言扩展包（GPT-SoVITS）",
            "",
            "把本压缩包里的 gpt_sovits 文件夹解压到程序的 resources 目录下，",
            "最终结构应为：",
            "",
            "  声纹工坊-v1.0.0\\resources\\gpt_sovits\\python\\python.exe",
            "  声纹工坊-v1.0.0\\resources\\gpt_sovits\\api_v2.py",
            "",
            "重启程序后，在右上角引擎下拉里选择「GPT-SoVITS · 多语言克隆」即可。",
            "",
            "支持语言：中文、英语、日语、韩语、粤语（零样本克隆）。",
            "首次合成会启动独立服务，约需 30~60 秒加载模型。",
            "",
            f"体积：约 2.6 GB（解压后），压缩包约 2.2 GB。",
            "",
            "许可：GPT-SoVITS 代码 MIT，可用于商业用途；",
            "使用他人音色请确保已获得授权。",
        ]), encoding="utf-8")

    log("扩展包目录就绪")
    return out_root


def build_zip(out_root: Path) -> Path:
    import zipfile

    zip_path = DIST / f"{PKG_NAME}.zip"
    if zip_path.exists():
        zip_path.unlink()
    files = [p for p in out_root.rglob("*") if p.is_file()]
    total = sum(p.stat().st_size for p in files)
    log(f"打包 {len(files)} 个文件 / {total / 1024 ** 3:.2f} GB -> {zip_path.name}")

    stored = {".dll", ".pyd", ".exe", ".whl", ".zip", ".pt", ".pth", ".ckpt",
              ".bin", ".onnx", ".dic", ".ftz", ".safetensors", ".gz"}
    done = 0
    t0 = time.time()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED,
                         compresslevel=1, allowZip64=True) as z:
        for i, f in enumerate(files, 1):
            arc = f.relative_to(out_root)
            try:
                if f.suffix.lower() in stored:
                    z.write(f, arc, compress_type=zipfile.ZIP_STORED)
                else:
                    z.write(f, arc, compress_type=zipfile.ZIP_DEFLATED, compresslevel=1)
            except (PermissionError, FileNotFoundError) as exc:
                log(f"  跳过 {arc}（{exc.__class__.__name__}）")
            done += f.stat().st_size if f.exists() else 0
            if i % 3000 == 0 or i == len(files):
                pct = 100 * done / max(1, total)
                speed = done / max(1e-6, time.time() - t0) / 1024 ** 2
                log(f"  {i}/{len(files)} {pct:5.1f}% {speed:5.1f} MB/s")

    size = zip_path.stat().st_size
    log(f"完成 {zip_path.name} {size / 1024 ** 3:.2f} GB，用时 {time.time() - t0:.0f}s")
    return zip_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-zip", action="store_true", help="只构建目录，不压缩")
    ap.add_argument("--zip-only", action="store_true", help="只压缩已构建好的目录")
    args = ap.parse_args()

    if args.zip_only:
        out_root = DIST / PKG_NAME
        if not (out_root / EXT_NAME).exists():
            print(f"找不到已构建的目录：{out_root}")
            return 2
        build_zip(out_root)
        return 0

    if not SRC_RUNTIME.exists() or not SRC_GS.exists():
        print("找不到源目录：E:\\Python310 或 E:\\Python310\\gs")
        return 2
    out_root = build_dir()
    if not args.no_zip:
        build_zip(out_root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
