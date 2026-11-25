# -*- coding: utf-8 -*-
"""F5-TTS 引擎：零样本音色克隆，原生支持中文 / 英文 / 中英混读。"""
from __future__ import annotations

import inspect
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional, Tuple

from ..config import CACHE_DIR, CONFIG, models_dir
from .base import Engine, SynthRequest

MODEL_NAME = "F5TTS_v1_Base"
MODEL_SIZE_HINT = "约 1.4 GB"


class _NullProgress:
    """替代 gradio.Progress；同时把批次进度转成界面可读的百分比。"""

    def __init__(self, cb: Optional[Callable[[float], None]] = None) -> None:
        self._cb = cb

    def __call__(self, *a, **k):
        return None

    def tqdm(self, iterable=None, *a, **k):
        if iterable is None:
            return []
        items = list(iterable)
        total = max(1, len(items))

        def _gen():
            for i, item in enumerate(items):
                if self._cb:
                    try:
                        self._cb(i / total)
                    except Exception:
                        pass
                yield item
            if self._cb:
                try:
                    self._cb(1.0)
                except Exception:
                    pass

        return _gen()


def _quiet(*a, **k):
    return None


def _setup_env() -> None:
    """配置 HuggingFace 镜像，便于国内网络下载模型。"""
    endpoint = CONFIG.get("hf_endpoint") or "https://hf-mirror.com"
    if endpoint:
        os.environ.setdefault("HF_ENDPOINT", endpoint)
    os.environ.setdefault("HF_HOME", str(models_dir()))
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    # hf-mirror 不支持 Xet 传输协议，关闭后改走普通 HTTPS，速度差异极大
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    os.environ.setdefault("MODELSCOPE_CACHE", str(CACHE_DIR / "modelscope"))

    # 让 pydub / 子进程能找到 ffmpeg（imageio-ffmpeg 自带一份）
    try:
        from ..audio_proc import ffmpeg_path
        exe = ffmpeg_path()
        if exe:
            _alias_ffmpeg(exe)
    except Exception:
        pass


def _alias_ffmpeg(exe: str) -> None:
    """imageio-ffmpeg 的二进制名不是 ffmpeg.exe，做个别名放进 PATH。"""
    packaged = os.environ.get("VCS_FFMPEG", "").strip()
    if packaged and Path(packaged).exists():
        os.environ.setdefault("FFMPEG_BINARY", packaged)
        folder = str(Path(packaged).parent)
        if folder not in os.environ.get("PATH", ""):
            os.environ["PATH"] = folder + os.pathsep + os.environ.get("PATH", "")
        return
    bin_dir = CACHE_DIR / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    target = bin_dir / "ffmpeg.exe"
    if not target.exists() or target.stat().st_size == 0:
        try:
            os.link(exe, target)
        except Exception:
            # 跨盘无法硬链接：不复制 100MB 副本，靠下面的 FFMPEG_BINARY 指路
            pass
    path = os.environ.get("PATH", "")
    if str(bin_dir) not in path:
        os.environ["PATH"] = str(bin_dir) + os.pathsep + path
    os.environ.setdefault("IMAGEIO_FFMPEG_EXE", exe)
    os.environ.setdefault("FFMPEG_BINARY", str(target))


def _patch_torchaudio() -> None:
    """torchaudio 2.9+ 的 load() 依赖 torchcodec，而 torchcodec 需要系统 FFmpeg 动态库。

    本机通常没有，改用 soundfile 解码即可，结果格式完全一致。
    """
    try:
        import torch
        import torchaudio
    except Exception:
        return
    try:
        if getattr(torchaudio.load, "__vcs_patched__", False):
            return

        def _load(path, **kwargs):
            import soundfile as sf
            data, sr = sf.read(str(path), dtype="float32", always_2d=True)
            return torch.from_numpy(data.T.copy()), int(sr)

        _load.__vcs_patched__ = True
        torchaudio.load = _load
    except Exception:
        pass


class F5TTSEngine(Engine):
    key = "f5tts"
    label = "F5-TTS · 零样本克隆"
    kind = "clone"
    description = ("非自回归 DiT 语音克隆模型，仅需 5~15 秒参考音频即可复刻音色，"
                   "原生支持中文、英文与中英混读，CPU 可运行。")
    packages = ["f5-tts"]
    needs_model = True

    def __init__(self) -> None:
        super().__init__()
        self._api = None
        self._loading = False

    # ------------------------------------------------------------------ #
    def available(self) -> Tuple[bool, str]:
        # 用 find_spec 探测，避免启动时真的去 import torch（耗时数秒）
        try:
            import importlib.util
            if importlib.util.find_spec("f5_tts") is None:
                return False, "未安装（需运行 pip install f5-tts）"
        except Exception:
            return False, "未安装（需运行 pip install f5-tts）"
        return True, "已安装" + ("，模型已加载" if self._api is not None else "，首次合成时加载模型")

    def unload(self) -> None:
        self._api = None
        self._ready = False
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    def load(self, progress: Optional[Callable[[str], None]] = None) -> None:
        if self._api is not None:
            return
        if self._loading:
            return
        self._loading = True
        try:
            _setup_env()
            if progress:
                progress(f"正在加载 F5-TTS（首次使用需下载模型 {MODEL_SIZE_HINT}）…")

            import torch
            threads = int(CONFIG.get("cpu_threads") or 0)
            if threads > 0:
                torch.set_num_threads(threads)
            else:
                torch.set_num_threads(max(1, (os.cpu_count() or 4)))
            os.environ.setdefault("OMP_NUM_THREADS", str(max(1, os.cpu_count() or 4)))

            _patch_torchaudio()

            from f5_tts.api import F5TTS

            sig = inspect.signature(F5TTS.__init__)
            kwargs = {}
            for k, v in (("model", MODEL_NAME),
                         ("device", CONFIG.get("device") or "cpu"),
                         ("hf_cache_dir", str(models_dir()))):
                if k in sig.parameters:
                    kwargs[k] = v
            self._api = F5TTS(**kwargs)
            self._ready = True
            if progress:
                progress("模型加载完成")
        finally:
            self._loading = False

    # ------------------------------------------------------------------ #
    def synth_chunk(self, text: str, req: SynthRequest, out_wav: Path) -> Path:
        if not req.ref_wav or not Path(req.ref_wav).exists():
            raise RuntimeError("缺少参考音频，请先在音色库创建音色")
        if not req.ref_text.strip():
            raise RuntimeError("该音色还没有参考文本，请在音色库中填写（或使用「自动识别」）")

        self.load(req.progress)
        out_wav.parent.mkdir(parents=True, exist_ok=True)

        ref_file = self._clamp_reference(Path(req.ref_wav))

        sig = inspect.signature(self._api.infer)
        kwargs = {
            "ref_file": str(ref_file),
            "ref_text": req.ref_text.strip(),
            "gen_text": text,
            "file_wave": str(out_wav),
            "nfe_step": int(req.nfe),
            "cfg_strength": float(req.cfg),
            "speed": float(req.speed),
            "target_rms": float(req.target_rms),
            "remove_silence": False,
            "seed": None if req.seed is None or req.seed < 0 else int(req.seed),
        }
        if "progress" in sig.parameters:
            def _sub(p: float) -> None:
                req.log(f"生成中… {int(p * 100)}%")
            kwargs["progress"] = _NullProgress(_sub)
        if "show_info" in sig.parameters:
            kwargs["show_info"] = _quiet
        if "device" in sig.parameters:
            kwargs["device"] = CONFIG.get("device") or "cpu"
        kwargs = {k: v for k, v in kwargs.items() if k in sig.parameters}

        self._api.infer(**kwargs)

        if not out_wav.exists() or out_wav.stat().st_size == 0:
            # 部分版本不写文件，改为接收返回值
            res = self._api.infer(**{**kwargs, "file_wave": None})
            if isinstance(res, tuple) and len(res) >= 2:
                import soundfile as sf
                sf.write(str(out_wav), res[0], int(res[1]))
        if not out_wav.exists():
            raise RuntimeError("合成失败：模型没有返回音频")
        return out_wav

    # ------------------------------------------------------------------ #
    @staticmethod
    def _clamp_reference(path: Path, max_sec: float = 20.0) -> Path:
        """F5-TTS 内部用 (22 - 参考时长) 估算每批字数，参考音频过长会得到负值。

        这里把超长参考音频截断，既规避该问题，也加快推理。
        """
        try:
            import soundfile as sf
            data, sr = sf.read(str(path), dtype="float32", always_2d=True)
            if len(data) / float(sr) <= max_sec:
                return path
            data = data[: int(max_sec * sr)]
            tmp = (Path(tempfile.gettempdir())
                   / f"vcs_ref_clip_{os.getpid()}_{int(time.time() * 1000)}.wav")
            sf.write(str(tmp), data, sr)
            return tmp
        except Exception:
            return path


class F5TTSEnvCheck:
    """环境自检信息，供设置页展示（只读元数据，不导入重型模块）。"""

    _cache: Optional[str] = None

    @staticmethod
    def report(force: bool = False) -> str:
        if F5TTSEnvCheck._cache is not None and not force:
            return F5TTSEnvCheck._cache
        from importlib.metadata import PackageNotFoundError, version
        lines = []
        for pkg in ("torch", "torchaudio", "transformers", "f5-tts"):
            try:
                lines.append(f"{pkg:<14} {version(pkg)}")
            except PackageNotFoundError:
                lines.append(f"{pkg:<14} 未安装")
            except Exception as exc:
                lines.append(f"{pkg:<14} 读取失败 ({type(exc).__name__})")
        F5TTSEnvCheck._cache = "\n".join(lines)
        return F5TTSEnvCheck._cache


# 模块导入即配置镜像，确保早于 huggingface_hub 的任何导入
_setup_env()
