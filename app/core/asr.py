# -*- coding: utf-8 -*-
"""参考文本自动识别（可选依赖 faster-whisper）。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Optional

from .config import CACHE_DIR, CONFIG


class ASRUnavailable(RuntimeError):
    pass


_MODEL = None
_MODEL_SIZE = ""


def available() -> tuple[bool, str]:
    try:
        import importlib.util
        if importlib.util.find_spec("faster_whisper") is None:
            return False, "未安装（可选，pip install faster-whisper）"
    except Exception:
        return False, "未安装（可选，pip install faster-whisper）"
    return True, "可用"


def transcribe(wav_path: str | Path,
               progress: Optional[Callable[[str], None]] = None,
               language: Optional[str] = None) -> str:
    """识别参考音频中的说话内容，用于音色克隆的参考文本。"""
    global _MODEL, _MODEL_SIZE
    try:
        from faster_whisper import WhisperModel
    except Exception as exc:
        raise ASRUnavailable(
            "自动识别需要安装 faster-whisper：pip install faster-whisper"
        ) from exc

    os.environ.setdefault("HF_ENDPOINT", CONFIG.get("hf_endpoint") or "https://hf-mirror.com")
    size = str(CONFIG.get("asr_model") or "base")
    if _MODEL is None or _MODEL_SIZE != size:
        if progress:
            progress(f"正在加载语音识别模型（{size}，首次需下载）…")
        device = "cuda" if _cuda_ok() else "cpu"
        _MODEL = WhisperModel(size, device=device, compute_type="int8",
                              download_root=str(CACHE_DIR / "whisper"))
        _MODEL_SIZE = size

    if progress:
        progress("正在识别参考音频…")

    # 关键：直接传 16kHz 单声道 numpy 数组，绕开 faster-whisper 内部的 PyAV 解码。
    # 它默认会走 av.open(..., metadata_errors="ignore")，而旧版 PyAV 没有这个参数，
    # 会抛 "open() got an unexpected keyword argument 'metadata_errors'"。
    audio_input: object = str(wav_path)
    try:
        from .audio_proc import read_audio, resample
        y, sr = read_audio(wav_path)
        if sr != 16000:
            y = resample(y, sr, 16000)
        audio_input = y.astype("float32")
    except Exception:
        audio_input = str(wav_path)   # 读不了就退回让 faster-whisper 自己解

    try:
        segments, info = _MODEL.transcribe(audio_input, language=None,
                                           vad_filter=True, beam_size=3)
        text = "".join(seg.text for seg in segments).strip()
    except TypeError as exc:
        if "metadata_errors" in str(exc):
            raise RuntimeError(
                "语音识别组件版本不匹配（PyAV 与 faster-whisper）。\n"
                "请在设置页重新安装「语音识别组件」，或改用更新的安装包。") from exc
        raise
    # 繁体转简体，避免克隆模型读错
    try:
        from opencc import OpenCC
        text = OpenCC("t2s").convert(text)
    except Exception:
        pass
    if not text:
        raise RuntimeError("没有识别到语音内容，请换一段更清晰的素材或手动填写")
    return text


def _cuda_ok() -> bool:
    try:
        import torch
        return bool(torch.cuda.is_available())
    except Exception:
        return False
