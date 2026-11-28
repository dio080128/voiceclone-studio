"""声纹工坊 · 启动器

职责：
  1. 检查 resources\\runtime 与 resources\\models 是否就位
  2. 缺失则弹进度窗口在线下载（支持多分卷、断点续传、SHA256 校验、自动解压）
  3. 就位后拉起 resources\\app\\main.py

打包：pyinstaller --onefile --windowed --name 声纹工坊 launcher_boot.py
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

APP_NAME = "声纹工坊"
UA = "VoiceCloneStudio/1.0 (Windows)"  # HTTP 头必须纯 ASCII，中文会抛 UnicodeEncodeError
CHUNK = 1024 * 256


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


ROOT = app_root()
RES = ROOT / "resources"


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{int(n)} B" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def load_cfg() -> dict:
    p = ROOT / "launcher" / "endpoints.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def build_tasks(cfg: dict) -> list[dict]:
    """把配置整理成任务列表。

    压缩包内路径自带 ``resources/`` 前缀，所以解压目标是 ROOT（安装根目录），
    而不是 RES，否则会解到 resources/resources/... 里。
    """
    tasks: list[dict] = []

    rt = cfg.get("runtime") or {}
    parts = rt.get("parts") or (
        [{"url": rt.get("url"), "sha256": rt.get("sha256")}] if rt.get("url") else []
    )
    parts = [p for p in parts if (p.get("url") or "").strip()]
    if parts:
        tasks.append({
            "key": "runtime",
            "name": "Python 运行时",
            "probe": RES / "runtime" / "python.exe",
            "dest": ROOT,
            "parts": parts,
            "hint": rt.get("size_hint") or "约 2.3 GB",
        })

    md = cfg.get("models") or {}
    if (md.get("url") or "").strip():
        tasks.append({
            "key": "models",
            "name": "语音模型 F5-TTS",
            "probe": RES / "models" / "models--SWivid--F5-TTS",
            "dest": ROOT,
            "parts": [{"url": md["url"], "sha256": md.get("sha256", ""), "label": "模型"}],
            "hint": md.get("size_hint") or "约 1.3 GB",
        })

    return tasks


def marker_of(task: dict) -> Path:
    return RES / f".ready_{task['key']}"


def task_ready(task: dict) -> bool:
    """解压完整才算就绪：优先看标记文件，兼容手动解压的老用户。"""
    return marker_of(task).exists() or task["probe"].exists()


def clean_legacy_garbage() -> None:
    """旧版本 bug 会把文件解到 resources/resources 下，这里清掉，避免白占几个 G。"""
    junk = RES / "resources"
    if not junk.is_dir():
        return
    for sub in ("runtime", "models"):
        target = junk / sub
        if target.is_dir():
            try:
                import shutil
                shutil.rmtree(target, ignore_errors=True)
            except Exception:
                pass
    try:
        if not any(junk.iterdir()):
            junk.rmdir()
    except Exception:
        pass


def _fatal(message: str) -> None:
    """没有控制台，错误必须弹窗，不能静默退出。"""
    try:
        import tkinter as tk
        from tkinter import messagebox as mb
        r = tk.Tk()
        r.withdraw()
        mb.showerror(f"{APP_NAME} · 启动失败", message)
        r.destroy()
    except Exception:
        pass


def launch_main() -> int:
    python = RES / "runtime" / "python.exe"
    script = RES / "app" / "main.py"
    if not python.exists() or not script.exists():
        missing = []
        if not python.exists():
            missing.append(str(python))
        if not script.exists():
            missing.append(str(script))
        _fatal("运行环境不完整，缺少：\n" + "\n".join(missing) +
               "\n\n请删掉安装目录重新安装，或重新运行本程序让它自动补齐。")
        return 2
    env = os.environ.copy()
    env["VCS_HOME"] = str(RES / "data")
    env["VCS_MODELS"] = str(RES / "models")
    ffmpeg = RES / "bin" / "ffmpeg.exe"
    if ffmpeg.exists():
        env["VCS_FFMPEG"] = str(ffmpeg)
    env["HF_ENDPOINT"] = "https://hf-mirror.com"
    env["HF_HUB_DISABLE_XET"] = "1"
    env["HF_HUB_DISABLE_TELEMETRY"] = "1"
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    log_dir = RES / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log = open(log_dir / "runtime.log", "a", encoding="utf-8", errors="replace")
    subprocess.Popen(
        [str(python), str(script)],
        cwd=str(ROOT),
        env=env,
        stdout=log,
        stderr=log,
        stdin=subprocess.DEVNULL,
        creationflags=0x08000000,
    )
    return 0


def download(url: str, dest: Path, on_progress) -> None:
    """流式下载，带断点续传。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    have = dest.stat().st_size if dest.exists() else 0
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    if have:
        req.add_header("Range", f"bytes={have}-")
    with urllib.request.urlopen(req, timeout=30) as resp:
        total = int(resp.headers.get("Content-Length") or 0) + have
        mode = "ab" if have and resp.status == 206 else "wb"
        if mode == "wb":
            have = 0
        with open(dest, mode) as f:
            got = have
            while True:
                block = resp.read(CHUNK)
                if not block:
                    break
                f.write(block)
                got += len(block)
                on_progress(got, total)


def _norm_name(name: str) -> str:
    """统一压缩包内的路径。

    历史分卷打包时前缀不一致，有的打到一半多套了一层：
        resources/runtime/...                  ← part1/2
        声纹工坊-v1.0.0/resources/runtime/...   ← part3/4/5
    统一从 resources/ 开始，保证解压后落在安装根目录的正确位置。
    """
    idx = name.find("resources/")
    if idx > 0:
        return name[idx:]
    return name


def unzip(src: Path, dest: Path, on_progress) -> None:
    dest.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(src) as zf:
        infos = zf.infolist()
        # 前缀规范时优先用系统自带 tar（bsdtar），对中文文件名比 zipfile 稳
        need_norm = any(i.filename.find("resources/") > 0 for i in infos)
        if not need_norm and os.name == "nt":
            try:
                subprocess.run(
                    ["tar", "-xf", str(src), "-C", str(dest)],
                    check=True, capture_output=True, creationflags=0x08000000,
                )
                on_progress(1, 1)
                return
            except Exception:
                pass

        total = len(infos)
        for i, info in enumerate(infos):
            name = _norm_name(info.filename)
            if not name:
                continue
            if not (info.flag_bits & 0x800):
                try:
                    name = name.encode("cp437").decode("gbk")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    pass
            target = dest / name
            if info.is_dir() or name.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as fp, open(target, "wb") as out:
                    while True:
                        block = fp.read(CHUNK)
                        if not block:
                            break
                        out.write(block)
            if i % 200 == 0:
                on_progress(i, total)


def run_gui() -> int:
    import tkinter as tk
    from tkinter import ttk

    cfg = load_cfg()
    tasks = build_tasks(cfg)
    if not tasks:
        return launch_main()

    clean_legacy_garbage()

    pending = [t for t in tasks if not task_ready(t)]
    if not pending:
        return launch_main()

    total_parts = sum(len(t["parts"]) for t in pending)

    root = tk.Tk()
    root.title(f"{APP_NAME} · 首次运行准备")
    root.geometry("540x280")
    root.resizable(False, False)
    root.configure(bg="#f5f6f8")
    try:
        root.iconbitmap(default=str(ROOT / "launcher" / "app.ico"))
    except Exception:
        pass

    tk.Label(root, text="首次运行需要下载依赖",
             font=("Microsoft YaHei UI", 14, "bold"),
             bg="#f5f6f8", fg="#1f2328").pack(pady=(24, 4))
    tk.Label(root,
             text="程序主体已就位，还需下载运行环境与语音模型。\n下载一次即可，之后打开无需联网。",
             font=("Microsoft YaHei UI", 9), bg="#f5f6f8", fg="#57606a",
             justify="center").pack()

    stage = tk.Label(root, text="准备中...", font=("Microsoft YaHei UI", 10),
                     bg="#f5f6f8", fg="#1f2328")
    stage.pack(pady=(20, 6))

    bar = ttk.Progressbar(root, length=460, mode="determinate")
    bar.pack()
    detail = tk.Label(root, text="", font=("Consolas", 8), bg="#f5f6f8", fg="#6e7781")
    detail.pack(pady=(6, 0))

    state = {"ok": False, "err": ""}

    def ui(fn):
        root.after(0, fn)

    def worker():
        done = 0
        try:
            for task in pending:
                for part in task["parts"]:
                    done += 1
                    url = part["url"].strip()
                    label = part.get("label") or ""
                    zip_path = Path(os.environ.get("TEMP", ".")) / f"vcs_{task['key']}_{done}.zip"

                    head = f"[{done}/{total_parts}] {task['name']}"
                    if label:
                        head += f" · {label}"
                    ui(lambda h=head, t=task: stage.config(text=f"{h}  ({t['hint']})"))

                    zip_path.unlink(missing_ok=True)
                    last = [0.0]

                    def cb(got, total):
                        if total <= 0:
                            return
                        pct = got * 100.0 / total
                        if time.time() - last[0] < 0.15:
                            return
                        last[0] = time.time()
                        ui(lambda: (bar.configure(value=pct),
                                    detail.config(text=f"{human(got)} / {human(total)}   {pct:.0f}%")))

                    ui(lambda: (bar.configure(value=0), detail.config(text="")))
                    download(url, zip_path, cb)

                    expect = (part.get("sha256") or "").strip().lower()
                    if expect:
                        ui(lambda: stage.config(text="校验文件完整性..."))
                        if sha256_of(zip_path).lower() != expect:
                            raise RuntimeError(f"{task['name']} 第 {done} 个包校验失败，文件可能损坏")

                    ui(lambda: stage.config(text=f"正在解压 {task['name']}..."))
                    unzip(zip_path, task["dest"], lambda i, tot: ui(
                        lambda: (bar.configure(value=i * 100.0 / max(tot, 1)),
                                 detail.config(text=f"{i} / {tot} 个文件"))))
                    zip_path.unlink(missing_ok=True)

                # 整组解压完才写标记，避免半截就判定"已就绪"
                try:
                    marker_of(task).write_text("ok", encoding="utf-8")
                except Exception:
                    pass

            ui(lambda: (bar.configure(value=100),
                        stage.config(text="全部就绪，正在启动..."),
                        detail.config(text="")))
            time.sleep(0.6)
            state["ok"] = True
            ui(root.destroy)
        except Exception as exc:  # noqa: BLE001
            state["err"] = str(exc)
            ui(root.destroy)

    threading.Thread(target=worker, daemon=True).start()
    root.mainloop()

    if state["ok"]:
        return launch_main()
    if state["err"]:
        import tkinter.messagebox as mb
        r = tk.Tk(); r.withdraw()
        mb.showerror(f"{APP_NAME} · 下载失败",
                     f"{state['err']}\n\n请检查网络后重新打开程序。\n"
                     f"也可以手动下载后解压到 resources 目录。")
        r.destroy()
    return 1


def main() -> int:
    try:
        return run_gui()
    except Exception:
        try:
            log_dir = RES / "data" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            import traceback
            (log_dir / "launcher_error.log").write_text(
                traceback.format_exc(), encoding="utf-8")
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
