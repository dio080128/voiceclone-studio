# -*- coding: utf-8 -*-
"""下载 bluearchive.wiki 上 Kei 的全部语音（ogg）。

页面被 Cloudflare 挡住，但媒体文件托管在 static.wikitide.net（不受挑战保护），
路径规则是 MediaWiki 标准的 /bluearchivewiki/<md5[0]>/<md5[:2]>/<文件名>。

另外本机环境变量里有 http_proxy=127.0.0.1:59189，对该 CDN 不通，
requests 会走代理导致连接失败 —— 必须 trust_env=False 直连。
"""
from __future__ import annotations

import hashlib
import re
import sys
import time
from pathlib import Path

import requests

HTML = Path(r"C:\Users\zm\AppData\Local\Temp\kei_page.html")
OUT = Path(r"E:\BlueArchive_Kei_Voice")
CDN = "https://static.wikitide.net/bluearchivewiki/{a}/{ab}/{name}"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0")


def main() -> int:
    html = HTML.read_text(encoding="utf-8", errors="ignore")
    names = list(dict.fromkeys(re.findall(r'data-mwtitle="([^"]+\.ogg)"', html)))
    print(f"页面中提取到 {len(names)} 个音频", flush=True)
    if not names:
        return 2

    OUT.mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    s.trust_env = False
    s.headers.update({"User-Agent": UA, "Referer": "https://bluearchive.wiki/"})

    ok = fail = skip = 0
    total_bytes = 0
    t0 = time.time()
    failed: list[str] = []

    for i, name in enumerate(names, 1):
        dst = OUT / name
        if dst.exists() and dst.stat().st_size > 1024:
            skip += 1
            continue
        h = hashlib.md5(name.replace(" ", "_").encode()).hexdigest()
        url = CDN.format(a=h[0], ab=h[:2], name=name)
        try:
            r = s.get(url, timeout=30)
            if r.status_code != 200 or not r.content.startswith(b"OggS"):
                raise RuntimeError(f"HTTP {r.status_code} len={len(r.content)}")
            dst.write_bytes(r.content)
            ok += 1
            total_bytes += len(r.content)
        except Exception as exc:
            fail += 1
            failed.append(f"{name}: {exc}")
            print(f"  ! {name} -> {exc}", flush=True)
        if i % 20 == 0 or i == len(names):
            print(f"  {i}/{len(names)}  成功 {ok} 跳过 {skip} 失败 {fail}", flush=True)

    print(f"\n完成：成功 {ok}，跳过 {skip}，失败 {fail}，"
          f"共 {total_bytes / 1024 ** 2:.1f} MB，用时 {time.time() - t0:.0f}s", flush=True)
    if failed:
        print("失败清单：", flush=True)
        for f in failed:
            print("  " + f, flush=True)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
