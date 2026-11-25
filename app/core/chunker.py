# -*- coding: utf-8 -*-
"""长文本切块：按语义边界切分，保证每块长度适中、不破坏英文单词。"""
from __future__ import annotations

import re
from typing import List

# 句末标点（一级边界）
SENT_END = "。！？!?…；;\n"
# 句中标点（二级边界）
CLAUSE_END = "，,、：:—"

_SENT_RE = re.compile(r"[^。！？!?…；;\n]+[。！？!?…；;\n]*|[。！？!?…；;\n]+")


def split_sentences(text: str) -> List[str]:
    """按句末标点切句，保留标点。"""
    out: List[str] = []
    for m in _SENT_RE.finditer(text):
        piece = m.group(0).strip()
        if piece:
            out.append(piece)
    return out


def _hard_split(piece: str, limit: int) -> List[str]:
    """在标点/空格处硬切，避免切坏英文单词。"""
    chunks: List[str] = []
    rest = piece
    while len(rest) > limit:
        window = rest[:limit]
        cut = -1
        for i in range(len(window) - 1, max(0, limit // 2), -1):
            if window[i] in CLAUSE_END:
                cut = i + 1
                break
        if cut < 0:
            for i in range(len(window) - 1, max(0, limit // 3), -1):
                if window[i] == " ":
                    cut = i + 1
                    break
        if cut < 0:
            cut = limit
        chunks.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    if rest:
        chunks.append(rest)
    return chunks


def chunk_text(text: str, max_chars: int = 110, min_chars: int = 14) -> List[str]:
    """把文本切成若干合成单元。

    Args:
        text: 已规范化的文本
        max_chars: 单块最大字符数
        min_chars: 过短的句子会与下一句合并
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    chunks: List[str] = []
    buf = ""
    for sent in split_sentences(text):
        if len(sent) > max_chars:
            if buf:
                chunks.append(buf.strip())
                buf = ""
            chunks.extend(_hard_split(sent, max_chars))
            continue
        if not buf:
            buf = sent
        elif len(buf) + len(sent) <= max_chars:
            buf += sent
        else:
            chunks.append(buf.strip())
            buf = sent
    if buf.strip():
        chunks.append(buf.strip())

    # 合并过短的尾块
    merged: List[str] = []
    for c in chunks:
        if merged and len(c) < min_chars and len(merged[-1]) + len(c) <= max_chars:
            merged[-1] += c
        else:
            merged.append(c)
    return [c for c in merged if c.strip()]
