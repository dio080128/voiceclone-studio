# -*- coding: utf-8 -*-
"""系统语音引擎（Windows SAPI）。

不克隆音色，用于无模型环境下跑通全流程与功能自测。
优先用 PowerShell 的 System.Speech 直接写 WAV（pyttsx3 在部分机器上只写空文件），
失败再回退到 pyttsx3。
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Tuple

from ..audio_proc import read_audio, resample, write_audio
from .base import Engine, SynthRequest

_PS_SCRIPT = r"""
param([string]$InFile, [string]$OutFile, [int]$Rate = 0, [int]$Volume = 100)
Add-Type -AssemblyName System.Speech
$text = [System.IO.File]::ReadAllText($InFile, [System.Text.Encoding]::UTF8)
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $s.Rate = [Math]::Max(-10, [Math]::Min(10, $Rate))
    $s.Volume = [Math]::Max(0, [Math]::Min(100, $Volume))
    $s.SetOutputToWaveFile($OutFile)
    $s.Speak($text)
} finally {
    $s.Dispose()
}
"""


def _powershell() -> str | None:
    for exe in ("powershell.exe", "pwsh.exe"):
        p = shutil.which(exe)
        if p:
            return p
    return None


class SystemEngine(Engine):
    key = "system"
    label = "系统语音 · 免模型"
    kind = "system"
    description = ("调用 Windows 内置语音合成，无需下载任何模型，可立即验证文本处理、"
                   "切句与导出流程；不支持音色克隆，仅作备用与测试。")
    packages = ["pyttsx3"]
    needs_model = False

    def __init__(self) -> None:
        super().__init__()
        self._voices: List[str] = []
        self._checked = False
        self._ok = False
        self._detail = ""

    # ------------------------------------------------------------------ #
    def available(self) -> Tuple[bool, str]:
        if self._checked:
            return self._ok, self._detail
        self._checked = True
        self._voices = self._list_voices()
        if _powershell() is None and not self._voices:
            self._ok = False
            self._detail = "未检测到可用的系统语音"
        else:
            self._ok = True
            cn = [v for v in self._voices if "chinese" in v.lower() or "huihui" in v.lower()]
            self._detail = (f"可用，{len(self._voices)} 个系统语音"
                            + ("（含中文）" if cn else "（无中文语音包）"))
        return self._ok, self._detail

    def voices(self) -> List[str]:
        self.available()
        return self._voices

    @staticmethod
    def _list_voices() -> List[str]:
        try:
            import pyttsx3
            eng = pyttsx3.init()
            names = [v.name for v in (eng.getProperty("voices") or [])]
            eng.stop()
            return names
        except Exception:
            return []

    # ------------------------------------------------------------------ #
    def synth_chunk(self, text: str, req: SynthRequest, out_wav: Path) -> Path:
        out_wav = Path(out_wav)
        out_wav.parent.mkdir(parents=True, exist_ok=True)
        tmpdir = Path(tempfile.mkdtemp(prefix="vcs_sapi_"))
        txt = tmpdir / "text.txt"
        txt.write_text(text, encoding="utf-8")
        raw = tmpdir / "raw.wav"

        ok = self._speak_powershell(txt, raw, req.speed)
        if not ok or not raw.exists() or raw.stat().st_size < 1000:
            self._speak_pyttsx3(text, raw, req.speed)

        if not raw.exists() or raw.stat().st_size < 1000:
            raise RuntimeError("系统语音合成失败：请确认 Windows 已安装语音包（设置→时间和语言→语音）")

        y, sr = read_audio(raw)
        y = resample(y, sr, 24000)
        write_audio(out_wav, y, 24000)
        return out_wav

    # ------------------------------------------------------------------ #
    def _speak_powershell(self, txt: Path, out: Path, speed: float) -> bool:
        ps = _powershell()
        if ps is None:
            return False
        script_path = txt.parent / "speak.ps1"
        script_path.write_text(_PS_SCRIPT, encoding="utf-8")
        rate = max(-10, min(10, int(round((speed - 1.0) * 8))))
        cmd = [ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
               str(script_path), "-InFile", str(txt), "-OutFile", str(out),
               "-Rate", str(rate)]
        try:
            subprocess.run(cmd, capture_output=True, timeout=180, check=False)
        except Exception:
            return False
        return out.exists() and out.stat().st_size > 1000

    def _speak_pyttsx3(self, text: str, out: Path, speed: float) -> None:
        try:
            import pyttsx3
        except Exception:
            return
        eng = pyttsx3.init()
        try:
            base = eng.getProperty("rate") or 200
            eng.setProperty("rate", max(60, int(base * float(speed))))
            eng.save_to_file(text, str(out))
            eng.runAndWait()
        except Exception:
            pass
        finally:
            try:
                eng.stop()
            except Exception:
                pass
