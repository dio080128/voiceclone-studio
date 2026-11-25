# -*- coding: utf-8 -*-
"""合成调度：文本规范化 -> 切块 -> 逐块推理 -> 拼接 -> 导出。"""
from __future__ import annotations

import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

import numpy as np

from .audio_proc import concat, normalize_rms, read_audio, to_mp3, write_audio
from .chunker import chunk_text
from .config import CACHE_DIR, CONFIG
from .engines.base import Engine, SynthRequest
from .profiles import VoiceProfile
from .textnorm import analyze, normalize

ProgressCB = Optional[Callable[[int, str], None]]
CancelCB = Optional[Callable[[], bool]]


class Cancelled(Exception):
    """用户取消合成。"""


@dataclass
class SynthResult:
    wav: Path
    duration: float = 0.0
    chunks: int = 0
    chars: int = 0
    engine: str = ""
    elapsed: float = 0.0
    mp3: Optional[Path] = None
    normalized_text: str = ""
    sample_rate: int = 24000


def prepare_text(raw: str, max_chars: int | None = None) -> List[str]:
    text = normalize(raw)
    return chunk_text(text, max_chars or int(CONFIG.get("max_chunk_chars") or 110))


def synthesize(raw_text: str,
               profile: Optional[VoiceProfile],
               engine: Engine,
               out_path: str | Path,
               *,
               speed: float = 1.0,
               nfe: int = 24,
               cfg: float = 2.0,
               seed: int = -1,
               gap_ms: float | None = None,
               max_chars: int | None = None,
               export_mp3: bool | None = None,
               progress_cb: ProgressCB = None,
               cancel_cb: CancelCB = None) -> SynthResult:

    def emit(pct: int, msg: str) -> None:
        if progress_cb:
            progress_cb(max(0, min(100, pct)), msg)

    def check_cancel() -> None:
        if cancel_cb and cancel_cb():
            raise Cancelled()

    t0 = time.time()
    normalized = normalize(raw_text)
    if not normalized.strip():
        raise ValueError("文本为空（规范化后没有可朗读内容）")

    chunks = chunk_text(normalized, max_chars or int(CONFIG.get("max_chunk_chars") or 110))
    if not chunks:
        raise ValueError("文本为空")

    if engine.kind == "clone" and profile is None:
        raise ValueError("当前引擎需要选择音色")
    if engine.kind == "clone" and profile is not None and not profile.ref_text.strip():
        raise ValueError("该音色缺少参考文本，无法克隆。请在音色库中填写参考文本。")

    tmp_dir = Path(tempfile.mkdtemp(prefix="vcs_syn_", dir=str(CACHE_DIR)))
    last_pct = [2]
    req = SynthRequest(
        text="", out_path=Path(out_path),
        ref_wav=str(profile.wav_path) if profile else "",
        ref_text=profile.ref_text if profile else "",
        language=profile.lang if profile else "auto",
        speed=speed, nfe=nfe, cfg=cfg, seed=seed,
        target_rms=float(CONFIG.get("target_rms") or 0.12),
        progress=lambda m: emit(last_pct[0], m),
        should_cancel=cancel_cb,
    )
    last_pct = [2]

    pieces: List[np.ndarray] = []
    total = len(chunks)
    emit(2, f"文本已切分为 {total} 段，开始合成…")
    try:
        for i, chunk in enumerate(chunks):
            check_cancel()
            last_pct[0] = int(4 + 90 * i / total)
            emit(last_pct[0], f"合成第 {i + 1}/{total} 段：{chunk[:18]}…")
            part = tmp_dir / f"part_{i:04d}.wav"
            engine.synth_chunk(chunk, req, part)
            if not part.exists() or part.stat().st_size == 0:
                raise RuntimeError(f"第 {i + 1} 段没有生成音频")
            y, sr = read_audio(part)
            if sr != 24000:
                from .audio_proc import resample
                y = resample(y, sr, 24000)
            pieces.append(y)

        check_cancel()
        emit(95, "拼接与响度归一…")
        gap = gap_ms if gap_ms is not None else float(CONFIG.get("gap_ms") or 180)
        audio = concat(pieces, 24000, gap_ms=gap)
        audio = normalize_rms(audio, float(CONFIG.get("target_rms") or 0.12))

        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        write_audio(out_path, audio, 24000)

        mp3_path = None
        want_mp3 = CONFIG.get("export_mp3") if export_mp3 is None else export_mp3
        if want_mp3:
            emit(98, "导出 MP3…")
            mp3_path = to_mp3(out_path, out_path.with_suffix(".mp3"))

        emit(100, "完成")
        return SynthResult(
            wav=out_path,
            duration=len(audio) / 24000,
            chunks=total,
            chars=len(normalized),
            engine=engine.label,
            elapsed=time.time() - t0,
            mp3=mp3_path,
            normalized_text=normalized,
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def text_report(raw: str) -> dict:
    """给界面用的文本检查报告。"""
    from .textnorm import unsupported_chars
    normalized = normalize(raw)
    stats = analyze(normalized)
    chunks = chunk_text(normalized, int(CONFIG.get("max_chunk_chars") or 110))
    unsupported = unsupported_chars(raw)
    return {
        "normalized": normalized,
        "stats": stats,
        "chunks": chunks,
        "unsupported": unsupported,
        "normalized_len": len(normalized),
    }
