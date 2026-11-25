# -*- coding: utf-8 -*-
r"""GPT-SoVITS 引擎（外部运行时）。

GPT-SoVITS 只支持 Python 3.9~3.10，依赖（pyopenjtalk / funasr / pytorch-lightning）
装不进主程序的 3.13 环境，因此走「独立运行时 + 本地 HTTP」的方式：

    resources/gpt_sovits/
        python.exe, Lib\...        独立的 Python 3.10
        api_v2.py, GPT_SoVITS\...  官方推理服务（这里以子进程形式拉起）
        GPT_SoVITS\pretrained_models\...

主程序只负责：启动服务 → POST /tts → 收 wav。这样主环境保持干净，
引擎崩了也不会拖垮界面。
"""
from __future__ import annotations

import atexit
import os
import re
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Optional, Tuple

import numpy as np

from ..audio_proc import read_audio, resample, write_audio
from ..config import DATA_ROOT, models_dir
from .base import Engine, SynthRequest

_CREATE_NO_WINDOW = 0x08000000

# 启动垫片：解决「_pth 让脚本目录脱离 sys.path」和「OpenJTalk 不认中文路径」两个问题。
# 后者是硬伤——open_jtalk 的 C 库用窄字符打开词典，路径里只要有中文就报
# "Failed to initialize Mecab"，而本程序目录就叫「声纹工坊」。
# 所以词典一旦发现位于非 ASCII 路径，就复制到纯英文目录再用。
_LAUNCHER_SRC = r'''# -*- coding: utf-8 -*-
"""由主程序生成：启动 GPT-SoVITS 的 api_v2。"""
import os
import shutil
import sys
import runpy
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

# jieba_fast 需要编译，装不上；用纯 Python 的 jieba 顶上（API 兼容）
try:
    import jieba
    import jieba.posseg
    sys.modules.setdefault("jieba_fast", jieba)
    sys.modules.setdefault("jieba_fast.posseg", jieba.posseg)
except Exception:
    pass


def _ascii_target() -> Path:
    """找一个纯英文、可写的目录存放词典。"""
    cands = []
    for env in ("ProgramData", "LOCALAPPDATA", "PUBLIC"):
        base = os.environ.get(env)
        if base:
            cands.append(Path(base) / "VoiceCloneStudio" / "ojdic")
    cands.append(Path(r"C:\ProgramData\VoiceCloneStudio\ojdic"))
    for c in cands:
        try:
            if not all(ord(ch) < 128 for ch in str(c)):
                continue
            c.mkdir(parents=True, exist_ok=True)
            probe = c / ".w"
            probe.write_bytes(b"1")
            probe.unlink()
            return c
        except Exception:
            continue
    return None


def _prepare_dict() -> None:
    site = Path(sys.executable).resolve().parent / "Lib" / "site-packages"
    src = site / "pyopenjtalk" / "open_jtalk_dic_utf_8-1.11"
    if not (src / "sys.dic").exists():
        return
    if all(ord(ch) < 128 for ch in str(src)):
        os.environ.setdefault("OPEN_JTALK_DICT_DIR", str(src))
        return
    dst = _ascii_target()
    if dst is None:
        return
    if not (dst / "sys.dic").exists():
        try:
            shutil.copytree(src, dst, dirs_exist_ok=True)
        except Exception:
            return
    os.environ["OPEN_JTALK_DICT_DIR"] = str(dst)


_prepare_dict()

sys.argv = [str(HERE / "api_v2.py")] + sys.argv[1:]
runpy.run_path(str(HERE / "api_v2.py"), run_name="__main__")
'''


def _guess_lang(text: str) -> str:
    """按字符集猜语言：假名→日语，谚文→韩语，汉字→中文，其余→英文。"""
    if re.search(r"[\u3040-\u30ff]", text):
        return "ja"
    if re.search(r"[\uac00-\ud7af]", text):
        return "ko"
    if re.search(r"[\u4e00-\u9fff]", text):
        return "zh"
    return "en"


_OOM_RE = re.compile(r"MemoryError|bad allocation|out of memory|DefaultCPUAllocator", re.I)


def diagnose_log(tail: str) -> str:
    """把日志尾部能认出来的故障翻译成一句人话；认不出来返回空串。

    这些判断只覆盖最常撞上的几种，认错了也只是多一句提示，不影响原始日志。
    """
    t = tail or ""
    if _OOM_RE.search(t):
        return ("看起来是内存不够：模型常驻约 4~5 GB，推理时还要再分配一块峰值内存。\n"
                "可以按顺序试：① 关掉浏览器等占内存的程序；② 确认系统虚拟内存（页面文件）"
                "没被关闭，建议设 12 GB 以上；③ 把「单段最大字符」调到 60~80 再合成。")
    if "Mecab" in t or "open_jtalk" in t:
        return ("日文分词词典初始化失败。常见原因是程序路径含中文，"
                "把整个程序目录移到纯英文路径下再试。")
    if "No module named" in t:
        return "扩展包缺少依赖，可能是拷贝时丢了文件，建议重新解压「多语言扩展包」。"
    if "Address already in use" in t or "WinError 10048" in t:
        return "端口被占用，关掉残留进程或重启软件后再试。"
    return ""


def _free_port(start: int = 19880) -> int:
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start


# 这套扩展包在 CPU 上跑，模型常驻约 4~5 GB，加载峰值更高。
# 低于这个物理内存总量就不必浪费时间了，必然 bad allocation。
MIN_TOTAL_RAM_MB = 5600


def memory_mb() -> tuple[int, int]:
    """返回 (物理内存总量 MB, 当前可用 MB)；取不到就返回 (0, 0)。"""
    try:
        import ctypes

        class _MemStat(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        st = _MemStat()
        st.dwLength = ctypes.sizeof(_MemStat)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
            return 0, 0
        return int(st.ullTotalPhys >> 20), int(st.ullAvailPhys >> 20)
    except Exception:
        return 0, 0


def low_ram_hint() -> str:
    """内存明显不够时返回一段说明，否则返回空串。"""
    total, avail = memory_mb()
    if not total or total >= MIN_TOTAL_RAM_MB:
        return ""
    return (f"这台机器只有 {total / 1024:.1f} GB 内存（当前可用 {avail / 1024:.1f} GB），"
            "跑不动多语言引擎。\n"
            "GPT-SoVITS 模型常驻就要 4~5 GB，加上系统占用需要 6 GB 以上，"
            "否则合成到一半必然 bad allocation。\n"
            "可选：① 加内存条（最实际，8 GB 起步）；"
            "② 换用 F5-TTS 引擎，中英文够用、占用小得多（4 GB 上仍然偏紧）；"
            "③ 把系统虚拟内存设到 16 GB 以上，再设环境变量 VCS_ALLOW_LOW_RAM=1 强制尝试"
            "（能出结果，但会很慢）。")


class GPTSoVITSEngine(Engine):
    key = "gptsovits"
    label = "GPT-SoVITS · 多语言克隆"
    kind = "clone"
    description = ("支持中/英/日/韩/粤零样本克隆，模型只有 F5 的 1/6，速度明显更快。"
                   "走独立运行时进程，首次合成会自动启动服务。")
    packages = []
    install_hint = ("需要另外的「多语言扩展包」（约 2.7 GB）：解压后得到 gpt_sovits 文件夹，"
                    "整个放进程序的 resources 目录，重启软件即可。"
                    "它自带 Python 3.10 运行时，不能用 pip 装进主程序。")
    needs_model = True

    def __init__(self) -> None:
        super().__init__()
        self._proc: Optional[subprocess.Popen] = None
        self._port: Optional[int] = None
        self._lock = threading.Lock()
        self._log_path: Optional[Path] = None
        atexit.register(self.unload)

    # ------------------------------------------------------------------ #
    def home(self) -> Optional[Path]:
        """定位独立运行时目录。"""
        cands = []
        env = os.environ.get("VCS_GPT_SOVITS", "").strip()
        if env:
            cands.append(Path(env))
        # 发行版：resources/gpt_sovits（data 的兄弟目录）
        cands.append(DATA_ROOT.parent / "gpt_sovits")
        # 开发机默认位置
        cands.append(Path(r"E:\Python310\gs"))
        for c in cands:
            try:
                if (c / "api_v2.py").exists():
                    return c
            except OSError:
                continue
        return None

    def python_exe(self, home: Optional[Path] = None) -> Optional[Path]:
        """独立运行时的解释器：发行版在 home/python/，开发机在 gs 的上一层。"""
        home = home or self.home()
        if home is None:
            return None
        for cand in (home / "python" / "python.exe", home / "python.exe",
                     home.parent / "python.exe"):
            try:
                if cand.exists():
                    return cand
            except OSError:
                continue
        return None

    def available(self) -> Tuple[bool, str]:
        home = self.home()
        if home is None:
            return False, ("未安装多语言扩展包：把「多语言扩展包」解压到程序的 "
                           "resources 目录（得到 resources/gpt_sovits）后重启即可")
        if self.python_exe(home) is None:
            return False, "扩展包不完整：缺少 python\\python.exe"
        model = home / "GPT_SoVITS" / "pretrained_models" / "gsv-v2final-pretrained" / "s2G2333k.pth"
        if not model.exists():
            return False, "扩展包不完整：缺少模型权重（pretrained_models）"
        if self._proc is not None and self._proc.poll() is None:
            return True, f"服务运行中（端口 {self._port}）"
        # 文件齐全不代表跑得动，内存明显不够时把警告挂进提示里
        warn = low_ram_hint()
        if warn and not os.environ.get("VCS_ALLOW_LOW_RAM"):
            return True, "已就绪，但内存不足，合成会失败。\n" + warn
        return True, "已就绪，首次合成时启动服务（约需 30 秒）"

    def unload(self) -> None:
        self._ready = False
        proc = self._proc
        self._proc = None
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    # ------------------------------------------------------------------ #
    def _start_server(self, progress: Optional[Callable[[str], None]]) -> None:
        home = self.home()
        if home is None:
            raise RuntimeError("找不到 GPT-SoVITS 运行环境（resources/gpt_sovits）")

        # 内存不够的机器：与其等它加载完再 bad allocation，不如现在就说清楚
        if not os.environ.get("VCS_ALLOW_LOW_RAM"):
            warn = low_ram_hint()
            if warn:
                raise RuntimeError(warn)

        python = self.python_exe(home)
        if python is None:
            raise RuntimeError("找不到运行时 python.exe")
        api = home / "api_v2.py"
        config = home / "GPT_SoVITS" / "configs" / "tts_infer.yaml"
        self._port = _free_port()

        log_dir = DATA_ROOT / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        self._log_path = log_dir / "gptsovits.log"
        logf = open(self._log_path, "a", encoding="utf-8", errors="replace")

        env = dict(os.environ)
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONNOUSERSITE"] = "1"
        env["HF_ENDPOINT"] = "https://hf-mirror.com"
        env["HF_HUB_DISABLE_XET"] = "1"
        env["HF_HOME"] = str(models_dir())
        # 子进程内部会用 urllib 下载 NLTK 等资源，本机的 http_proxy 对它不通
        for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
                  "ALL_PROXY", "all_proxy"):
            env.pop(k, None)
        env["NO_PROXY"] = "*"
        env["no_proxy"] = "*"

        # 嵌入式 Python 的 _pth 会让脚本目录脱离 sys.path，用垫片脚本补上。
        # 每次启动都重写，保证逻辑与主程序版本一致。
        launcher = home / "launch_api.py"
        launcher.write_text(_LAUNCHER_SRC, encoding="utf-8")

        cmd = [str(python), str(launcher), "-a", "127.0.0.1", "-p", str(self._port),
               "-c", str(config)]
        self._proc = subprocess.Popen(
            cmd, cwd=str(home), env=env, stdout=logf, stderr=subprocess.STDOUT,
            creationflags=_CREATE_NO_WINDOW)

        if progress:
            progress("正在启动多语言引擎（首次约 30~60 秒）…")

        deadline = time.time() + 240
        import json
        import urllib.request
        while time.time() < deadline:
            if self._proc.poll() is not None:
                code = self._proc.returncode
                tail = self.log_tail(1500)
                msg = f"引擎启动失败（退出码 {code}）"
                tip = diagnose_log(tail)
                if tip:
                    msg += "\n" + tip
                raise RuntimeError(msg + ("\n" + tail if tail else ""))
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{self._port}/openapi.json", timeout=3) as r:
                    if r.status == 200:
                        json.loads(r.read().decode("utf-8"))
                        if progress:
                            progress("引擎已就绪")
                        return
            except Exception:
                time.sleep(1.5)
        raise RuntimeError("引擎启动超时（240 秒），请查看 resources/data/logs/gptsovits.log")

    def log_tail(self, n: int = 1200) -> str:
        """引擎日志最后 n 个字符，拼进错误提示里方便定位。"""
        try:
            if self._log_path is not None and self._log_path.exists():
                return self._log_path.read_text(encoding="utf-8", errors="replace")[-n:]
        except Exception:
            pass
        return ""

    def _ensure_server(self, progress=None) -> None:
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                return
            self._start_server(progress)

    # ------------------------------------------------------------------ #
    def _prepare_ref(self, src: Path) -> Path:
        """GPT-SoVITS 要求参考音频 3~10 秒，超出就截取/补足到合法区间。"""
        from ..config import CACHE_DIR

        y, sr = read_audio(src)
        dur = len(y) / float(sr)
        if 3.0 <= dur <= 10.0:
            return src
        if dur > 10.0:
            y = y[: int(9.5 * sr)]
        out = CACHE_DIR / f"gs_ref_{src.stem[:24]}_{int(dur * 10)}.wav"
        write_audio(out, np.ascontiguousarray(y, dtype=np.float32), sr)
        return out

    def synth_chunk(self, text: str, req: SynthRequest, out_wav: Path) -> Path:
        import requests

        self._ensure_server(req.log)
        ref = Path(req.ref_wav)
        if not ref.is_absolute():
            ref = ref.resolve()
        ref = self._prepare_ref(ref)

        payload = {
            "text": text,
            "text_lang": _guess_lang(text),
            "ref_audio_path": str(ref),
            "prompt_text": req.ref_text or "",
            "prompt_lang": _guess_lang(req.ref_text or text),
            "text_split_method": "cut5",
            "batch_size": 1,
            "speed_factor": max(0.5, min(2.0, float(req.speed))),
            "media_type": "wav",
            "streaming_mode": False,
            # 4 核机器上并行推理只会互相抢核，关掉更稳
            "parallel_infer": False,
            "seed": int(req.seed) if req.seed is not None else -1,
        }
        url = f"http://127.0.0.1:{self._port}/tts"
        req.log(f"合成中（{payload['text_lang']}）…")
        t0 = time.time()
        # 本机直连：系统里若配了 http_proxy，requests 会把 localhost 也转发过去
        sess = requests.Session()
        sess.trust_env = False
        try:
            r = sess.post(url, json=payload, timeout=1800)
        except Exception as exc:
            # 服务在合成过程中死掉（最常见的是内存被撑爆）时，
            # requests 只会抛 ConnectionError，这里补一句人话再抛出去。
            tail = self.log_tail(1500)
            tip = diagnose_log(tail) or ("引擎服务在合成途中退出了，"
                                         "重启软件后再试；反复出现请查看引擎日志。")
            raise RuntimeError(f"引擎服务无响应：{exc.__class__.__name__}\n{tip}"
                               + (f"\n{tail}" if tail else ""))
        if r.status_code != 200 or len(r.content) < 1024:
            detail = r.text[:300] if r.content else "(空响应)"
            tip = diagnose_log(detail + self.log_tail(1500))
            raise RuntimeError("引擎返回异常 "
                               f"{r.status_code}: {detail}" + (f"\n{tip}" if tip else ""))

        out_wav = Path(out_wav)
        out_wav.parent.mkdir(parents=True, exist_ok=True)
        out_wav.write_bytes(r.content)

        # 统一成 24kHz 单声道，方便和其它引擎的切块结果拼接
        y, sr = read_audio(out_wav)
        if sr != 24000:
            y = resample(y, sr, 24000)
        write_audio(out_wav, np.ascontiguousarray(y, dtype=np.float32), 24000)
        req.log(f"本段完成（{time.time() - t0:.1f}s）")
        return out_wav
