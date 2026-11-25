# -*- coding: utf-8 -*-
"""从 bluearchive.wiki 抓某个角色的全部语音（ogg）。

页面本身被 Cloudflare 挡着，普通请求拿不到，所以先用无头 Edge 导出 DOM：

    msedge --headless=new --virtual-time-budget=25000 --dump-dom \
           "https://bluearchive.wiki/wiki/<角色>/audio" > page.html

本脚本负责后半段：从 DOM 里取出 <audio data-mwtitle>，按 MediaWiki 的
md5 路径规则拼出 static.wikitide.net 上的真实地址并下载。

注意：本机环境变量里有不通的 http_proxy，requests 必须 trust_env=False 直连，
否则对 CDN 会返回 HTTP 000。

用法：
    python tools/fetch_wiki_voice.py Hina --html page.html
    python tools/fetch_wiki_voice.py Yuuka --html page.html --out E:\\某目录
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
import time
from pathlib import Path

import requests

CDN = "https://static.wikitide.net/bluearchivewiki/{a}/{ab}/{name}"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("character", help="角色英文名，例如 Hina / Yuuka / Kei")
    ap.add_argument("--html", required=True, help="无头浏览器导出的页面 DOM")
    ap.add_argument("--out", default="", help="输出目录，默认 E:\\BlueArchive_<角色>_Voice")
    args = ap.parse_args()

    html_path = Path(args.html)
    if not html_path.exists():
        print(f"找不到页面文件：{html_path}")
        return 2
    html = html_path.read_text(encoding="utf-8", errors="ignore")
    names = list(dict.fromkeys(re.findall(r'data-mwtitle="([^"]+\.ogg)"', html)))
    print(f"{args.character}: 页面中 {len(names)} 个不重复音频", flush=True)
    if not names:
        return 2

    out = Path(args.out) if args.out else Path(rf"E:\BlueArchive_{args.character}_Voice")
    out.mkdir(parents=True, exist_ok=True)

    s = requests.Session()
    s.trust_env = False          # 绕开本机那个不通的代理
    s.headers.update({"User-Agent": UA, "Referer": "https://bluearchive.wiki/"})

    ok = skip = fail = 0
    total = 0
    failed: list[str] = []
    done = 0
    lock = __import__("threading").Lock()
    t0 = time.time()

    def one(name: str) -> None:
        nonlocal ok, skip, fail, total, done
        dst = out / name
        if dst.exists() and dst.stat().st_size > 1024:
            with lock:
                skip += 1
                done += 1
            return
        h = hashlib.md5(name.replace(" ", "_").encode()).hexdigest()
        url = CDN.format(a=h[0], ab=h[:2], name=name)
        err = ""
        for attempt in range(3):
            try:
                r = s.get(url, timeout=45)
                if r.status_code != 200 or not r.content.startswith(b"OggS"):
                    raise RuntimeError(f"HTTP {r.status_code} len={len(r.content)}")
                dst.write_bytes(r.content)
                with lock:
                    ok += 1
                    total += len(r.content)
                break
            except Exception as exc:
                err = str(exc)
                if attempt == 2:
                    with lock:
                        fail += 1
                        failed.append(f"{name}: {err}")
        with lock:
            done += 1
            if done % 25 == 0 or done == len(names):
                print(f"  {done}/{len(names)}  成功 {ok} 跳过 {skip} 失败 {fail}", flush=True)

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=5) as ex:
        list(ex.map(one, names))

    print(f"完成：成功 {ok}，跳过 {skip}，失败 {fail}，"
          f"{total / 1024 ** 2:.2f} MB，用时 {time.time() - t0:.0f}s")
    print(f"目录：{out}")
    for f in failed[:10]:
        print("  失败 " + f)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
