# -*- coding: utf-8 -*-
"""核心功能自检：文本规范化 / 切句 / 音频处理（不依赖界面与深度学习模型）。

用法：python tools/selftest.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from app.core.audio_proc import (analyze_quality, detect_segments, preprocess,
                                 read_audio, write_audio)
from app.core.chunker import chunk_text
from app.core.textnorm import analyze, normalize, unsupported_chars

CASES = [
    ("全角与标点", "Ｔｅｓｔ　全角ＡＢＣ，这是（测试）！"),
    ("数字读法", "订单 2026-11-09 已发货，共 3 件，合计 ¥1280.50，增长 12.5%。"),
    ("英文数字", "There are 1234 apples and 42 oranges, total 1276."),
    ("时间与区间", "会议 9:30 开始，持续 2-3 小时，电话 13800138000。"),
    ("中英混排", "打开 Python3.13 运行 F5-TTS，speed=1.0 效果最好。"),
    ("表情符号", "太棒了🎉🎉 这个功能真的很好用👍，下次见～"),
    ("数学符号", "面积 5×6=30 平方米，温度 18℃ ± 2°。"),
    ("零宽字符", "看不见的\u200b字符\u200d应该被清掉"),
]

LONG_TEXT = (
    "声音克隆技术近年来发展迅速。它通过少量参考音频，学习说话人的音色特征。"
    "传统的语音合成系统需要数小时的录音数据，而现在只需要 5 到 15 秒。"
    "This makes personalized voice assistants much more accessible. "
    "不过，这项技术也带来了新的伦理挑战：如何防止声音被滥用，是整个行业必须回答的问题。"
)


def main() -> int:
    print("=" * 72)
    print("① 文本规范化")
    print("=" * 72)
    for name, src in CASES:
        out = normalize(src)
        st = analyze(out)
        bad = unsupported_chars(out)
        print(f"\n[{name}]")
        print(f"  输入: {src}")
        print(f"  输出: {out}")
        print(f"  统计: {st.summary()}" + (f" | 可疑字符: {''.join(bad)}" if bad else ""))

    print()
    print("=" * 72)
    print("② 长文本切句")
    print("=" * 72)
    chunks = chunk_text(normalize(LONG_TEXT), 60)
    print(f"共 {len(chunks)} 段：")
    for i, c in enumerate(chunks):
        print(f"  {i + 1:>2}. [{len(c):>3}字] {c}")

    print()
    print("=" * 72)
    print("③ 音频处理")
    print("=" * 72)
    sr = 44100
    rng = np.random.default_rng(0)
    # 静音 0.5s + 三个 1.2s 音节段（带底噪）+ 静音 0.5s
    silence = np.zeros(int(sr * 0.5), dtype=np.float32)
    noise = rng.normal(0, 0.003, int(sr * 0.5)).astype(np.float32)
    tone = lambda f, d: (0.4 * np.sin(2 * np.pi * f * np.arange(int(sr * d)) / sr)).astype(np.float32)
    body = np.concatenate([tone(180, 1.2), noise[: int(sr * 0.35)], tone(220, 1.2),
                           noise[: int(sr * 0.35)], tone(260, 1.2)])
    y = np.concatenate([silence, body, silence])

    tmp = Path(tempfile.mkdtemp(prefix="vcs_selftest_"))
    src = tmp / "raw.wav"
    write_audio(src, y, sr)

    q_raw = analyze_quality(*read_audio(src), path=str(src))
    print(f"原始素材: {q_raw.duration:.2f}s / {q_raw.sr}Hz / "
          f"峰值 {q_raw.peak_db:.1f}dB / 评分 {q_raw.score}({q_raw.verdict})")

    out_wav, q = preprocess(src, tmp / "ref.wav")
    y2, sr2 = read_audio(out_wav)
    print(f"预处理后: {len(y2) / sr2:.2f}s / {sr2}Hz / 评分 {q.score}({q.verdict})")

    segs = detect_segments(*read_audio(src), min_silence=0.3, min_seg=0.5)
    print(f"静音切段: 检出 {len(segs)} 段 -> " +
          ", ".join(f"{s / sr:.2f}-{e / sr:.2f}s" for s, e in segs))

    print()
    print("=" * 72)
    print("④ 引擎状态")
    print("=" * 72)
    from app.core.engines.registry import all_engines
    for e in all_engines():
        ok, msg = e.available()
        print(f"  {'✓' if ok else '×'} {e.label:<26} {msg}")

    print("\n自检完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
