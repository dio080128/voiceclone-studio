# -*- coding: utf-8 -*-
"""从「基沃托斯古书馆」(kivo.wiki) 下载角色的**国服（中文）配音**。

蓝档案国服有独立的中配，这个站把每句语音的音频 + 中文台词都整理好了，
接口是 https://api.kivo.wiki/api/v1/data/students/<角色ID>，
返回的 data.voice_cn 即为国服语音数组，每项包含：
    description —— 语义化文件名（hina_battle_buffed_1.ogg）
    text        —— 这句的中文台词
    file        —— 真实地址（//static.kivo.wiki/...，随机 ID 命名）

顺带把「文件名 -> 台词」写成 台词清单.txt，建音色时直接复制即可，
不用再手动听写或跑语音识别。

用法：
    python tools/fetch_kivo_voice.py 71 日奈
    python tools/fetch_kivo_voice.py 52 优香 --out E:\\某目录
"""
from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

API = "https://api.kivo.wiki/api/v1/data/students/{cid}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cid", type=int, help="角色 ID，例如 日奈=71 优香=52 凯伊=518")
    ap.add_argument("name", help="角色中文名，用于命名输出目录")
    ap.add_argument("--out", default="", help="输出目录，默认 E:\\BlueArchive_<名字>_CN")
    args = ap.parse_args()

    s = requests.Session()
    s.trust_env = False
    s.headers.update({"Referer": "https://kivo.wiki/", "User-Agent": "Mozilla/5.0"})

    print(f"请求角色 {args.cid}（{args.name}）…", flush=True)
    r = s.get(API.format(cid=args.cid), timeout=30)
    r.raise_for_status()
    data = r.json().get("data") or {}
    items = data.get("voice_cn") or []
    if not items:
        print(f"国服没有语音数据（角色可能尚未在国服实装）")
        return 3

    out = Path(args.out) if args.out else Path(rf"E:\BlueArchive_{args.name}_CN")
    out.mkdir(parents=True, exist_ok=True)
    print(f"国服语音 {len(items)} 条 -> {out}", flush=True)

    ok = skip = fail = 0
    lines: list[str] = []
    failed: list[str] = []

    def one(item: dict) -> None:
        nonlocal ok, skip, fail
        desc = (item.get("description") or "").strip()
        url = (item.get("file") or "").strip()
        text = (item.get("text") or "").strip()
        if not url:
            return
        if not desc:
            desc = Path(url).name
        if not desc.lower().endswith((".ogg", ".mp3", ".wav")):
            desc += ".ogg"
        if url.startswith("//"):
            url = "https:" + url
        dst = out / desc
        if dst.exists() and dst.stat().st_size > 1024:
            skip += 1
        else:
            for attempt in range(3):
                try:
                    rr = s.get(url, timeout=45)
                    if rr.status_code != 200 or len(rr.content) < 512:
                        raise RuntimeError(f"HTTP {rr.status_code} len={len(rr.content)}")
                    dst.write_bytes(rr.content)
                    ok += 1
                    break
                except Exception as exc:
                    if attempt == 2:
                        fail += 1
                        failed.append(f"{desc}: {exc}")
        if text:
            lines.append(f"{desc}\t{text}")

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=5) as ex:
        list(ex.map(one, items))

    # 台词清单：按文件名排序，方便对照
    lines.sort()
    txt = out / "台词清单.txt"
    txt.write_text(
        f"{args.name} · 国服配音台词清单（{len(lines)} 条）\n"
        "格式：音频文件名 <TAB> 中文台词\n"
        "建音色时，把对应那一行的台词复制进「参考文本」即可。\n\n"
        + "\n".join(lines) + "\n",
        encoding="utf-8")

    print(f"完成：成功 {ok}，跳过 {skip}，失败 {fail}，用时 {time.time() - t0:.0f}s")
    print(f"音频目录：{out}")
    print(f"台词清单：{txt}")
    for f in failed[:8]:
        print("  失败 " + f)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
