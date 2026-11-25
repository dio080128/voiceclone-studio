# -*- coding: utf-8 -*-
"""构建便携发行版：小体积 exe 启动器 + resources 资源目录。

产物结构：
    声纹工坊-v1.0.0/
        声纹工坊.exe            <- 几十 KB 的纯 Win32 启动器
        使用说明.txt
        VERSION.txt
        resources/
            app/                程序代码（main.py + app/）
            runtime/            独立 Python 3.13 + 全部第三方包
            bin/ffmpeg.exe      音视频转码
            models/             F5-TTS 权重（可选，不带则首次运行自动下载）
            data/               voices / output / cache / logs / config.json

用法：
    python tools/build_release.py --out E:/VCS-Release --no-models
    python tools/build_release.py --out E:/VCS-Release --with-models --force
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROJ = Path(__file__).resolve().parents[1]
VERSION = "1.0.0"
APP_TITLE = f"声纹工坊-v{VERSION}"
MARKER = ".vcs_release"

GCC_CANDIDATES = [
    r"E:\qtcreator\Tools\mingw1310_64\bin\gcc.exe",
    r"C:\msys64\mingw64\bin\gcc.exe",
]
WRES_CANDIDATES = [
    r"E:\qtcreator\Tools\mingw1310_64\bin\windres.exe",
    r"C:\msys64\mingw64\bin\windres.exe",
]


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def find_tool(which: str, candidates: list[str]) -> str:
    p = shutil.which(which)
    if p:
        return p
    for c in candidates:
        if Path(c).exists():
            return c
    raise SystemExit(f"找不到 {which}，请确认 MinGW 工具链已安装")


def robocopy(src: Path, dst: Path, xd=(), xf=()) -> None:
    """用 robocopy 批量复制（跨盘大目录比 shutil 快一个数量级）。"""
    dst.mkdir(parents=True, exist_ok=True)
    args = ["robocopy", str(src), str(dst), "/E", "/MT:8", "/R:1", "/W:1",
            "/NFL", "/NDL", "/NJH", "/NJS", "/NP"]
    for d in xd:
        args += ["/XD", str(d)]
    for f in xf:
        args += ["/XF", f]
    r = subprocess.run(args, capture_output=True, text=True, errors="replace")
    if r.returncode >= 8:
        raise SystemExit(f"复制失败 {src} -> {dst}\n{r.stdout[-1500:]}")


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.exists():
        shutil.copy2(src, dst)


def dir_size(p: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(p):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f}{unit}" if unit != "B" else f"{n}B"
        n /= 1024
    return f"{n:.1f}GB"


# --------------------------------------------------------------------------- #
# 各构建步骤
# --------------------------------------------------------------------------- #

def step_prepare(out: Path, force: bool) -> Path:
    root = out / APP_TITLE
    if root.exists():
        if (root / MARKER).exists():
            log("检测到已有构建产物，执行增量更新（想完全重建请先删除该目录）")
        elif force:
            log(f"清理旧产物 {root}")
            shutil.rmtree(root, ignore_errors=True)
        else:
            raise SystemExit(f"目标已存在且不是本脚本产物：{root}\n"
                             f"确认要覆盖请加 --force")
    root.mkdir(parents=True, exist_ok=True)
    (root / MARKER).write_text(VERSION, encoding="utf-8")
    return root


def step_code(root: Path) -> None:
    log("复制程序代码 -> resources/app")
    app_dir = root / "resources" / "app"
    app_dir.mkdir(parents=True, exist_ok=True)
    copy_file(PROJ / "main.py", app_dir / "main.py")
    robocopy(PROJ / "app", app_dir / "app",
             xd=("__pycache__",), xf=("*.pyc", "*.pyo"))
    # 记录一下自检脚本与文档，便于排查
    docs = root / "docs"
    docs.mkdir(exist_ok=True)
    for name in ("README.md",):
        copy_file(PROJ / name, docs / name)
    robocopy(PROJ / "tools", docs / "tools", xd=("__pycache__",), xf=("*.pyc",))


def step_runtime(root: Path) -> None:
    base = Path(sys.base_prefix)
    log(f"复制 Python 运行时 <- {base}")
    rt = root / "resources" / "runtime"
    rt.mkdir(parents=True, exist_ok=True)

    for name in ("python.exe", "pythonw.exe", "python3.dll", "python313.dll",
                 "vcruntime140.dll", "vcruntime140_1.dll"):
        copy_file(base / name, rt / name)

    log("  标准库 Lib/")
    # 只剔除确定用不到的 GUI/兼容层；test、unittest 必须保留 ——
    # torch.utils._config_module 会 import unittest，删了直接崩。
    robocopy(base / "Lib", rt / "Lib",
             xd=("site-packages", "tkinter", "idlelib", "lib2to3",
                 "ensurepip", "turtledemo", "__pycache__"),
             xf=("*.pyc", "*.pyo"))

    log("  扩展模块 DLLs/")
    robocopy(base / "DLLs", rt / "DLLs", xd=("__pycache__",),
             xf=("*.pdb", "_tkinter.pyd", "tcl*.dll", "tk*.dll", "zlib1.dll.bak"))

    venv_sp = PROJ / ".venv" / "Lib" / "site-packages"
    if not venv_sp.exists():
        raise SystemExit("找不到虚拟环境依赖：.venv/Lib/site-packages")
    log("  第三方包 site-packages/（约 2~3GB，请稍候）")
    robocopy(venv_sp, rt / "Lib" / "site-packages", xd=("__pycache__",),
             xf=("*.pyc", "*.pyo", "*.pdb"))


def step_ffmpeg(root: Path) -> None:
    log("复制 ffmpeg")
    try:
        import imageio_ffmpeg
        src = Path(imageio_ffmpeg.get_ffmpeg_exe())
        copy_file(src, root / "resources" / "bin" / "ffmpeg.exe")
    except Exception as exc:
        log(f"  跳过（{exc}）")


def step_models(root: Path, with_models: bool) -> None:
    dst = root / "resources" / "models"
    dst.mkdir(parents=True, exist_ok=True)
    if not with_models:
        log("跳过模型（首次运行会自动下载到 resources/models）")
        (dst / "README.txt").write_text(
            "本目录用于存放 F5-TTS 模型权重（约 1.4GB）。\n"
            "当前发行包未预置模型，首次合成时会自动从这里下载。\n", encoding="utf-8")
        return
    src = PROJ / "cache" / "hf"
    if not src.exists():
        log("  本地没有模型缓存，跳过")
        return
    log("复制模型权重（约 1.4GB）")
    robocopy(src, dst, xd=(".locks", "xet"), xf=("*.lock", "*.incomplete"))


def step_data(root: Path) -> None:
    log("初始化数据目录")
    data = root / "resources" / "data"
    for sub in ("output", "cache", "logs", "voices"):
        (data / sub).mkdir(parents=True, exist_ok=True)

    # 清掉上次运行/测试留下的缓存与日志，避免把临时文件打进发行包
    for sub in ("cache", "logs"):
        d = data / sub
        for child in d.iterdir():
            try:
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink()
            except Exception:
                pass

    # 发行包不带开发机上的音色（用户第一次打开是干净的空库）
    for v in (data / "voices").iterdir():
        try:
            if v.is_dir():
                shutil.rmtree(v, ignore_errors=True)
            else:
                v.unlink()
        except Exception:
            pass

    # 配置不写死输出路径，让程序按新位置初始化
    cfg = data / "config.json"
    if cfg.exists():
        try:
            cfg.unlink()
        except Exception:
            pass


def step_icon(root: Path) -> Path | None:
    """生成 exe 图标（用 Qt 画，再用 Pillow 转 ico）。"""
    ico = root / "launcher" / "app.ico"
    ico.parent.mkdir(parents=True, exist_ok=True)
    if ico.exists():
        return ico
    try:
        from PySide6.QtCore import QSize  # noqa: F401
        code = (
            "import sys; sys.path.insert(0, r'%s')\n"
            "from PySide6.QtWidgets import QApplication\n"
            "from app.ui.theme import make_app_icon\n"
            "app = QApplication(sys.argv)\n"
            "pm = make_app_icon(256).pixmap(256, 256)\n"
            "pm.save(r'%s')\n" % (PROJ, ico.with_suffix(".png"))
        )
        subprocess.run([sys.executable, "-c", code], check=True)
        from PIL import Image
        img = Image.open(ico.with_suffix(".png")).convert("RGBA")
        img.save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                             (64, 64), (128, 128), (256, 256)])
        return ico
    except Exception as exc:
        log(f"  图标生成失败（{exc}），使用默认图标")
        return None


def step_build_exe(root: Path) -> None:
    log("编译启动器")
    gcc = find_tool("gcc", GCC_CANDIDATES)
    windres = find_tool("windres", WRES_CANDIDATES)
    src = PROJ / "launcher" / "launcher.c"
    if not src.exists():
        raise SystemExit("缺少 launcher/launcher.c")

    ico = step_icon(root)
    res_o = root / "launcher" / "launcher_res.o"
    if ico:
        rc = root / "launcher" / "launcher.rc"
        rc.write_text(
            '1 ICON "%s"\n'
            '1 VERSIONINFO\n'
            'FILEVERSION 1,0,0,0\n'
            'PRODUCTVERSION 1,0,0,0\n'
            'FILEOS 0x40004\n'
            'FILETYPE 0x1\n'
            'BEGIN\n'
            '  BLOCK "StringFileInfo"\n'
            '  BEGIN\n'
            '    BLOCK "080404B0"\n'
            '    BEGIN\n'
            '      VALUE "CompanyName", "VoiceClone Studio"\n'
            '      VALUE "FileDescription", "VoiceClone Studio Launcher"\n'
            '      VALUE "ProductName", "VoiceClone Studio"\n'
            '      VALUE "FileVersion", "1.0.0.0"\n'
            '      VALUE "ProductVersion", "1.0.0.0"\n'
            '    END\n'
            '  END\n'
            '  BLOCK "VarFileInfo"\n'
            '  BEGIN\n'
            '    VALUE "Translation", 0x804, 1200\n'
            '  END\n'
            'END\n' % ico.name,
            encoding="utf-8")
        subprocess.run([windres, str(rc.name), "-o", str(res_o)],
                       cwd=str(rc.parent), check=True)

    out_exe = root / "声纹工坊.exe"
    cmd = [gcc, "-O2", "-s", "-municode", "-mwindows", str(src), "-o", str(out_exe)]
    if res_o.exists():
        cmd.append(str(res_o))
    subprocess.run(cmd, check=True)
    log(f"  {out_exe.name}  {human(out_exe.stat().st_size)}")


def step_docs(root: Path, with_models: bool) -> None:
    log("写说明文件")
    (root / "VERSION.txt").write_text(
        f"声纹工坊 VoiceClone Studio v{VERSION}\n"
        f"构建时间：{time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"模型：{'已预置' if with_models else '未预置（首次合成时自动下载）'}\n"
        f"引擎：F5-TTS 1.1.22 (CC-BY-NC) + Windows SAPI\n",
        encoding="utf-8")

    (root / "使用说明.txt").write_text(
        """声纹工坊 VoiceClone Studio v1.0.0  —— 使用说明
================================================================

【怎么启动】
  双击「声纹工坊.exe」即可。
  注意：exe 必须和 resources 文件夹放在一起，不要单独把 exe 复制走。

【第一次使用】
  1. 打开「音色库」→「新建音色（导入素材）」
  2. 添加 5~15 秒清晰人声（可多选，软件会自动挑最好的一条）
  3. 点「开始分析与预处理」
  4. 在「参考文本」里填写这段音频里实际说的话（可点自动识别）
  5. 起个名字 →「创建音色」
  6. 回到「语音合成」，选音色、输入文本 →「开始合成」

【关于速度（重要）】
  本软件用 F5-TTS 做零样本音色克隆，纯 CPU 运行时较慢：
    推理步数 24：30 字左右约 10 分钟
    推理步数 8 ：15 字左右约 2~3 分钟
  合成时界面会显示「已用时 N 秒」，不是卡死。建议把推理步数调到 8~12。
  有 NVIDIA 显卡（8G 显存以上）可提速数十倍，需要换 CUDA 版 PyTorch。

【首次合成会联网下载模型】
  约 1.4GB，从 hf-mirror.com 镜像拉取，下载位置 resources\\models。
  想离线使用，就把别人机器上的 resources\\models 整个复制过来。

【目录说明】
  resources\\app      程序本体
  resources\\runtime  Python 运行环境（勿删改）
  resources\\models   模型权重
  resources\\data     你的数据：音色、合成结果、配置、日志
     data\\voices      音色档案
     data\\output      合成出来的音频
     data\\logs        出错日志（反馈问题时请附上 error.log）

【常见问题】
  · 双击没反应 / 弹出「缺少运行环境」
    压缩包没解压完整，或只复制了 exe。请整体解压后再运行。
  · 提示缺少中文语音
    Windows 设置 → 时间和语言 → 语音 → 添加中文语音包（仅系统语音引擎需要）。
  · 合成出来不像
    参考文本必须和参考音频逐字对应；换一段更干净、情绪平稳的素材。
  · 杀毒软件报毒
    启动器只是普通的程序调用，如被拦截请添加信任。

【使用边界】
  请只克隆你拥有授权的声音。不得用于伪造他人身份、诈骗或侵权。
  对外发布合成音频时，请标注「AI 合成」。
  F5-TTS 模型权重为 CC-BY-NC 许可，不可用于商业用途。
""", encoding="utf-8")


# --------------------------------------------------------------------------- #

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=r"E:\VoiceCloneStudio-Release")
    ap.add_argument("--with-models", action="store_true")
    ap.add_argument("--no-models", dest="with_models", action="store_false")
    ap.add_argument("--force", action="store_true")
    ap.set_defaults(with_models=False)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    root = step_prepare(out, args.force)

    step_code(root)
    step_runtime(root)
    step_ffmpeg(root)
    step_models(root, args.with_models)
    step_data(root)
    step_build_exe(root)
    step_docs(root, args.with_models)

    log("统计体积")
    parts = [("exe", root / "声纹工坊.exe"),
             ("app", root / "resources" / "app"),
             ("runtime", root / "resources" / "runtime"),
             ("models", root / "resources" / "models"),
             ("data", root / "resources" / "data")]
    for name, p in parts:
        size = p.stat().st_size if p.is_file() else dir_size(p)
        print(f"    {name:<10}{human(size):>10}")
    print(f"    合计      {human(dir_size(root)):>10}")
    log(f"完成，用时 {time.time() - t0:.0f}s -> {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
