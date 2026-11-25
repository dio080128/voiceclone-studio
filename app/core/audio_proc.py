# -*- coding: utf-8 -*-
"""音频 I/O 与预处理：解码、重采样、静音裁剪、响度归一、分句切割、质量评估。

优先使用 soundfile（libsndfile 1.2+ 内建 mp3/ogg/flac 支持）；
遇到 m4a/mp4/aac 等格式时自动回退到 imageio-ffmpeg 自带的 ffmpeg。
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import soundfile as sf

TARGET_SR = 24000
AUDIO_EXTS = {".wav", ".mp3", ".flac", ".ogg", ".opus", ".m4a", ".aac", ".wma", ".aiff", ".aif"}


# --------------------------------------------------------------------------- #
# ffmpeg 定位
# --------------------------------------------------------------------------- #

def ffmpeg_path() -> Optional[str]:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    exe = shutil.which("ffmpeg")
    return exe


def _ffmpeg_convert(src: Path, dst: Path, sr: int = TARGET_SR) -> bool:
    exe = ffmpeg_path()
    if not exe:
        return False
    cmd = [exe, "-y", "-i", str(src), "-ac", "1", "-ar", str(sr),
           "-c:a", "pcm_s16le", str(dst)]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=180, check=False)
        return dst.exists() and dst.stat().st_size > 0
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# 基础读写
# --------------------------------------------------------------------------- #

def read_audio(path: str | Path) -> Tuple[np.ndarray, int]:
    """读取音频为 float32 单声道，返回 (samples, sr)。"""
    path = Path(path)
    try:
        data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    except Exception:
        tmp = Path(tempfile.gettempdir()) / f"vcs_dec_{path.stem}.wav"
        if not _ffmpeg_convert(path, tmp):
            raise RuntimeError(f"无法解码音频：{path.name}（请安装 ffmpeg 或转换格式）")
        data, sr = sf.read(str(tmp), dtype="float32", always_2d=True)
        try:
            tmp.unlink()
        except Exception:
            pass
    y = data.mean(axis=1) if data.shape[1] > 1 else data[:, 0]
    return np.ascontiguousarray(y, dtype=np.float32), int(sr)


def write_audio(path: str | Path, y: np.ndarray, sr: int, subtype: str = "PCM_16") -> Path:
    """写 16bit PCM wav。soundfile 出问题（版本/扩展不匹配）时退回标准库 wave。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    y = np.asarray(y, dtype=np.float32)
    try:
        sf.write(str(path), y, sr, subtype=subtype)
        return path
    except Exception:
        import wave

        pcm = (np.clip(y, -1.0, 1.0) * 32767.0).astype("<i2")
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(int(sr))
            w.writeframes(pcm.tobytes())
        return path


def to_mp3(wav_path: str | Path, mp3_path: str | Path, bitrate: str = "192k") -> Optional[Path]:
    exe = ffmpeg_path()
    if not exe:
        return None
    cmd = [exe, "-y", "-i", str(wav_path), "-b:a", bitrate, str(mp3_path)]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=180, check=False)
        return Path(mp3_path) if Path(mp3_path).exists() else None
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# 信号处理
# --------------------------------------------------------------------------- #

def resample(y: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    if sr_in == sr_out or y.size == 0:
        return y.astype(np.float32)
    try:
        from math import gcd
        from scipy.signal import resample_poly
        g = gcd(int(sr_in), int(sr_out))
        return resample_poly(y, sr_out // g, sr_in // g).astype(np.float32)
    except Exception:
        pass
    # 线性插值兜底
    n_out = int(round(len(y) * sr_out / sr_in))
    x_old = np.linspace(0, 1, len(y), endpoint=False)
    x_new = np.linspace(0, 1, n_out, endpoint=False)
    return np.interp(x_new, x_old, y).astype(np.float32)


def rms(y: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(y)))) if y.size else 0.0


def db(x):
    if isinstance(x, np.ndarray):
        return 20.0 * np.log10(np.maximum(x.astype(np.float32), 1e-8))
    return 20.0 * np.log10(max(float(x), 1e-8))


def peak(y: np.ndarray) -> float:
    return float(np.max(np.abs(y))) if y.size else 0.0


def normalize_peak(y: np.ndarray, target_db: float = -1.5) -> np.ndarray:
    p = peak(y)
    if p < 1e-6:
        return y
    return (y * (10 ** (target_db / 20.0) / p)).astype(np.float32)


def normalize_rms(y: np.ndarray, target_rms: float = 0.12) -> np.ndarray:
    r = rms(y)
    if r < 1e-6:
        return y
    out = y * (target_rms / r)
    p = peak(out)
    if p > 0.98:
        out = out * (0.98 / p)
    return out.astype(np.float32)


def _frame_energy(y: np.ndarray, sr: int, win_ms: float = 25.0) -> Tuple[np.ndarray, int]:
    win = max(1, int(sr * win_ms / 1000))
    if len(y) < win:
        return np.array([rms(y)]), win
    n = len(y) // win
    frames = y[: n * win].reshape(n, win)
    return np.sqrt(np.mean(frames ** 2, axis=1)), win


def trim_silence(y: np.ndarray, sr: int, thresh_db: float = -42.0,
                 pad_ms: float = 60.0) -> np.ndarray:
    """基于帧能量裁剪首尾静音，保留少量余量避免吞字。"""
    if y.size == 0:
        return y
    energy, win = _frame_energy(y, sr)
    if energy.size == 0:
        return y
    level = db(float(np.max(energy)))
    thresh = max(level + thresh_db, db(float(np.percentile(energy, 5))) + 6.0)
    mask = energy > 10 ** (thresh / 20.0)
    if not mask.any():
        return y
    idx = np.where(mask)[0]
    pad = int(sr * pad_ms / 1000)
    start = max(0, idx[0] * win - pad)
    end = min(len(y), (idx[-1] + 1) * win + pad)
    return y[start:end]


def fade(y: np.ndarray, sr: int, ms: float = 15.0) -> np.ndarray:
    n = min(int(sr * ms / 1000), len(y) // 2)
    if n <= 0:
        return y
    y = y.copy()
    ramp = np.linspace(0.0, 1.0, n, dtype=np.float32)
    y[:n] *= ramp
    y[-n:] *= ramp[::-1]
    return y


def dc_remove(y: np.ndarray) -> np.ndarray:
    return (y - float(np.mean(y))).astype(np.float32)


def detect_segments(y: np.ndarray, sr: int, min_silence: float = 0.30,
                    min_seg: float = 1.0, thresh_db: float = -40.0
                    ) -> List[Tuple[int, int]]:
    """基于静音检测切出语音段（采样点区间）。"""
    energy, win = _frame_energy(y, sr)
    if energy.size < 3:
        return [(0, len(y))]
    floor = db(float(np.percentile(energy, 10))) + 6.0
    top = db(float(np.percentile(energy, 95)))
    # 与语音峰值挂钩的动态门限，避免底噪被误判为语音
    thresh = max(min(floor, top - 8.0), top - 25.0)
    voiced = energy > 10 ** (thresh / 20.0)

    segs: List[Tuple[int, int]] = []
    min_sil_frames = max(1, int(min_silence * sr / win))
    start = None
    silent_run = 0
    for i, v in enumerate(voiced):
        if v:
            if start is None:
                start = i
            silent_run = 0
        else:
            if start is not None:
                silent_run += 1
                if silent_run >= min_sil_frames:
                    end = i - silent_run + 1
                    if (end - start) * win >= min_seg * sr:
                        segs.append((start * win, end * win))
                    start = None
                    silent_run = 0
    if start is not None:
        end = len(voiced)
        if (end - start) * win >= min_seg * sr:
            segs.append((start * win, min(end * win, len(y))))
    return segs or [(0, len(y))]


def concat(chunks: List[np.ndarray], sr: int, gap_ms: float = 180.0,
           crossfade_ms: float = 20.0) -> np.ndarray:
    """拼接多段音频，带静音间隔与短交叉淡化，避免爆音。"""
    chunks = [c for c in chunks if c is not None and len(c) > 0]
    if not chunks:
        return np.zeros(int(sr * 0.1), dtype=np.float32)
    if len(chunks) == 1:
        return chunks[0]

    gap = np.zeros(int(sr * gap_ms / 1000), dtype=np.float32)
    nf = int(sr * crossfade_ms / 1000)
    out = chunks[0]
    for c in chunks[1:]:
        if nf > 0 and len(out) > nf and len(c) > nf:
            a, b = out[-nf:], c[:nf]
            ramp = np.linspace(0, 1, nf, dtype=np.float32)
            out = np.concatenate([out[:-nf], a * (1 - ramp) + b * ramp, c[nf:], ])
        else:
            out = np.concatenate([out, c])
        out = np.concatenate([out, gap])
    return out


def denoise(y: np.ndarray, sr: int, strength: float = 1.0) -> np.ndarray:
    """简易谱减法降噪（无额外依赖），适合底噪明显的录音。"""
    if y.size < sr // 4:
        return y
    n_fft, hop = 1024, 256
    window = np.hanning(n_fft).astype(np.float32)
    n_frames = 1 + (len(y) - n_fft) // hop
    if n_frames < 4:
        return y

    frames = np.lib.stride_tricks.as_strided(
        y, shape=(n_frames, n_fft), strides=(y.strides[0] * hop, y.strides[0])
    ) * window
    spec = np.fft.rfft(frames, axis=1)
    mag = np.abs(spec)
    phase = np.angle(spec)

    frame_e = mag.mean(axis=1)
    noise_idx = np.argsort(frame_e)[: max(3, n_frames // 10)]
    noise_mag = mag[noise_idx].mean(axis=0, keepdims=True)

    cleaned = np.maximum(mag - strength * noise_mag, mag * 0.06)
    spec_new = cleaned * np.exp(1j * phase)

    out = np.zeros(len(y), dtype=np.float32)
    norm = np.zeros(len(y), dtype=np.float32)
    for i in range(n_frames):
        seg = np.fft.irfft(spec_new[i], n=n_fft).astype(np.float32) * window
        out[i * hop: i * hop + n_fft] += seg
        norm[i * hop: i * hop + n_fft] += window ** 2
    norm[norm < 1e-6] = 1.0
    return (out / norm).astype(np.float32)


# --------------------------------------------------------------------------- #
# 质量评估
# --------------------------------------------------------------------------- #

@dataclass
class AudioQuality:
    path: str = ""
    duration: float = 0.0
    sr: int = 0
    channels: int = 1
    peak_db: float = -120.0
    rms_db: float = -120.0
    snr_db: float = 0.0
    clip_ratio: float = 0.0
    silence_ratio: float = 0.0
    score: int = 0
    issues: List[str] = field(default_factory=list)
    selected: bool = False

    @property
    def verdict(self) -> str:
        if self.score >= 85:
            return "优秀"
        if self.score >= 70:
            return "良好"
        if self.score >= 50:
            return "可用"
        return "较差"


def analyze_quality(y: np.ndarray, sr: int, path: str = "") -> AudioQuality:
    q = AudioQuality(path=path, sr=sr, duration=len(y) / sr if sr else 0.0)
    if y.size == 0:
        q.issues.append("音频为空")
        return q

    q.peak_db = db(peak(y))
    q.rms_db = db(rms(y))
    q.clip_ratio = float(np.mean(np.abs(y) > 0.995))

    energy, win = _frame_energy(y, sr)
    if energy.size > 4:
        noise = float(np.percentile(energy, 10))
        signal = float(np.percentile(energy, 90))
        q.snr_db = float(db(signal) - db(noise)) if noise > 1e-8 else 40.0
        thresh = db(signal) - 25.0
        q.silence_ratio = float(np.mean(db(np.maximum(energy, 1e-8)) < thresh))

    score = 100.0
    if q.duration < 3:
        score -= (3 - q.duration) * 12
        q.issues.append("素材偏短，建议 5 秒以上")
    elif q.duration > 25:
        score -= min(12, (q.duration - 25) * 0.5)
        q.issues.append("素材较长，将自动截取最佳片段")
    if q.snr_db < 15:
        score -= (15 - q.snr_db) * 1.6
        q.issues.append("底噪偏高")
    if q.clip_ratio > 0.002:
        score -= min(25, q.clip_ratio * 3000)
        q.issues.append("存在削波失真")
    if q.rms_db < -32:
        score -= (-32 - q.rms_db) * 1.2
        q.issues.append("音量偏小")
    if q.silence_ratio > 0.55:
        score -= (q.silence_ratio - 0.55) * 40
        q.issues.append("静音过多")
    if q.sr < 16000:
        score -= 10
        q.issues.append("采样率偏低")
    q.score = int(max(0, min(100, round(score))))
    return q


# --------------------------------------------------------------------------- #
# 音色素材预处理
# --------------------------------------------------------------------------- #

@dataclass
class PreprocessOptions:
    target_sr: int = TARGET_SR
    trim: bool = True
    normalize: bool = True
    denoise: bool = False
    auto_pick: bool = True
    min_sec: float = 4.0
    max_sec: float = 12.0
    target_rms: float = 0.12


def preprocess(path: str | Path, out_path: str | Path,
               opt: PreprocessOptions | None = None) -> Tuple[Path, AudioQuality]:
    """把任意素材处理成 24kHz 单声道干净参考音频。"""
    opt = opt or PreprocessOptions()
    y, sr = read_audio(path)
    y = dc_remove(y)

    if opt.trim:
        y = trim_silence(y, sr)

    if opt.auto_pick and len(y) / sr > opt.max_sec:
        y = _pick_best_window(y, sr, opt.min_sec, opt.max_sec)

    y = resample(y, sr, opt.target_sr)
    sr = opt.target_sr

    if opt.denoise:
        y = denoise(y, sr)

    if opt.normalize:
        y = normalize_rms(y, opt.target_rms)
        y = normalize_peak(y, -1.5)

    y = fade(y, sr)
    out_path = write_audio(out_path, y, sr)
    q = analyze_quality(y, sr, str(out_path))
    return out_path, q


def _pick_best_window(y: np.ndarray, sr: int, min_sec: float, max_sec: float) -> np.ndarray:
    """在长素材中挑选语音最连续、能量最稳定的一段。"""
    segs = detect_segments(y, sr, min_silence=0.25, min_seg=min_sec)
    if segs:
        # 优先选长度落在 [min_sec, max_sec] 的段，其次选最接近 8 秒的
        best = None
        best_cost = 1e9
        for s, e in segs:
            dur = (e - s) / sr
            if dur < min_sec * 0.6:
                continue
            cost = abs(min(dur, max_sec) - 8.0)
            if min_sec <= dur <= max_sec:
                cost -= 3.0
            if cost < best_cost:
                best_cost, best = cost, (s, e)
        if best:
            s, e = best
            seg = y[s:e]
            if len(seg) / sr > max_sec:
                seg = seg[: int(max_sec * sr)]
            return seg

    # 兜底：取能量最高的滑动窗口
    win = min(len(y), int(8 * sr))
    step = max(1, int(0.25 * sr))
    best_start, best_e = 0, -1.0
    for s in range(0, max(1, len(y) - win + 1), step):
        e = float(np.mean(np.square(y[s:s + win])))
        if e > best_e:
            best_e, best_start = e, s
    return y[best_start: best_start + win]


def build_reference(src_files: List[str | Path], out_wav: Path,
                    opt: PreprocessOptions | None = None
                    ) -> Tuple[Path, AudioQuality, List[Tuple[str, AudioQuality]]]:
    """从一批素材中选出最好的一条，输出为参考音频。

    返回 (参考音频路径, 该音频质量, 所有素材的评估结果)
    """
    opt = opt or PreprocessOptions()
    reports: List[Tuple[str, AudioQuality]] = []
    tmp_dir = Path(tempfile.mkdtemp(prefix="vcs_ref_"))
    best_path: Optional[Path] = None
    best_q: Optional[AudioQuality] = None
    best_score = -1.0
    best_idx = -1

    for i, src in enumerate(src_files):
        try:
            tmp_out = tmp_dir / f"cand_{i}.wav"
            y, sr = read_audio(src)
            q_raw = analyze_quality(y, sr, str(src))
            p, q = preprocess(src, tmp_out, opt)
            reports.append((str(src), q_raw))
            if q.score > best_score:
                best_score, best_path, best_q = q.score, p, q
                best_idx = len(reports) - 1
        except Exception as exc:  # 单个文件坏了不影响整体
            bad = AudioQuality(path=str(src))
            bad.issues.append(f"读取失败：{exc}")
            reports.append((str(src), bad))

    if best_path is None or best_q is None:
        raise RuntimeError("没有可用的音频素材")

    if best_idx >= 0:
        reports[best_idx][1].selected = True

    out_wav.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(best_path, out_wav)
    try:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception:
        pass
    return out_wav, best_q, reports
