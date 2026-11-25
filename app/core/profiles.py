# -*- coding: utf-8 -*-
"""音色档案：把参考音频 + 文本 + 元信息保存成一个可复用的「音色」。"""
from __future__ import annotations

import json
import shutil
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

from .audio_proc import TARGET_SR, read_audio
from .config import VOICES_DIR


@dataclass
class VoiceProfile:
    id: str = ""
    name: str = "未命名音色"
    lang: str = "mix"
    ref_text: str = ""
    duration: float = 0.0
    sr: int = TARGET_SR
    quality: int = 0
    created: str = ""
    note: str = ""
    sources: List[str] = field(default_factory=list)

    @property
    def dir(self) -> Path:
        return VOICES_DIR / self.id

    @property
    def wav_path(self) -> Path:
        return self.dir / "reference.wav"

    @property
    def display(self) -> str:
        return f"{self.name}  ·  {self.duration:.1f}s  ·  {self.quality}分"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "VoiceProfile":
        allowed = {f for f in cls().__dict__}
        return cls(**{k: v for k, v in d.items() if k in allowed})


class VoiceStore:
    """音色库，落盘于 voices/<id>/。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or VOICES_DIR)
        self.root.mkdir(parents=True, exist_ok=True)

    def list(self) -> List[VoiceProfile]:
        items: List[VoiceProfile] = []
        for d in sorted(self.root.iterdir()):
            if not d.is_dir():
                continue
            meta = d / "meta.json"
            if not meta.exists():
                continue
            try:
                p = VoiceProfile.from_dict(json.loads(meta.read_text(encoding="utf-8")))
                p.id = p.id or d.name
                if p.wav_path.exists():
                    items.append(p)
            except Exception:
                continue
        items.sort(key=lambda p: p.created, reverse=True)
        return items

    def get(self, vid: str) -> Optional[VoiceProfile]:
        for p in self.list():
            if p.id == vid:
                return p
        return None

    def create(self, name: str, ref_wav: str | Path, ref_text: str,
               quality: int = 0, lang: str = "mix",
               sources: List[str] | None = None, note: str = "") -> VoiceProfile:
        vid = time.strftime("%Y%m%d%H%M%S") + "_" + uuid.uuid4().hex[:6]
        d = self.root / vid
        d.mkdir(parents=True, exist_ok=True)
        dst = d / "reference.wav"
        shutil.copyfile(ref_wav, dst)
        try:
            y, sr = read_audio(dst)
            dur, sr_val = len(y) / sr, sr
        except Exception:
            dur, sr_val = 0.0, TARGET_SR

        profile = VoiceProfile(
            id=vid, name=name.strip() or "未命名音色", lang=lang,
            ref_text=ref_text.strip(), duration=dur, sr=sr_val,
            quality=quality, created=time.strftime("%Y-%m-%d %H:%M:%S"),
            note=note, sources=[str(s) for s in (sources or [])][:50],
        )
        self.save(profile)
        return profile

    def save(self, profile: VoiceProfile) -> None:
        d = profile.dir
        d.mkdir(parents=True, exist_ok=True)
        (d / "meta.json").write_text(
            json.dumps(profile.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def delete(self, vid: str) -> None:
        d = self.root / vid
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
