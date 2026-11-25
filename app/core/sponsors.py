# -*- coding: utf-8 -*-
"""鸣谢名单：本地缓存 + 定期更新。

数据由 tools/fetch_sponsors.py 从爱发电抓取后写入
`resources/data/sponsors.json`，界面只负责读取展示。
抓取失败不影响使用——没有文件就显示默认致谢语。
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import List

from .config import DATA_ROOT

SPONSOR_FILE = DATA_ROOT / "sponsors.json"


@dataclass
class Sponsor:
    name: str = ""
    avatar: str = ""
    months: int = 0          # 连续支持月数（爱发电提供时才有）
    since: str = ""          # 首次支持时间


@dataclass
class SponsorBoard:
    updated: str = ""        # 数据日期
    source: str = ""         # 来源主页
    total: int = 0           # 累计支持人数（可能大于展示数）
    sponsors: List[Sponsor] = field(default_factory=list)


def load() -> SponsorBoard:
    """读取名单；文件缺失或损坏时返回空板，不让界面报错。"""
    try:
        raw = json.loads(SPONSOR_FILE.read_text(encoding="utf-8"))
    except Exception:
        return SponsorBoard()
    board = SponsorBoard(
        updated=str(raw.get("updated") or ""),
        source=str(raw.get("source") or ""),
        total=int(raw.get("total") or 0),
    )
    for it in raw.get("sponsors") or []:
        if isinstance(it, dict) and it.get("name"):
            board.sponsors.append(Sponsor(
                name=str(it.get("name")),
                avatar=str(it.get("avatar") or ""),
                months=int(it.get("months") or 0),
                since=str(it.get("since") or ""),
            ))
        elif isinstance(it, str):
            board.sponsors.append(Sponsor(name=it))
    if not board.total:
        board.total = len(board.sponsors)
    return board


def save(board: SponsorBoard) -> None:
    SPONSOR_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(board)
    SPONSOR_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
