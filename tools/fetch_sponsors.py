# -*- coding: utf-8 -*-
"""抓取爱发电的赞助者名单，写入 <data>/sponsors.json 供「鸣谢名单」界面读取。

流程（两步，都是公开接口，不需要登录、不需要 cookie）：
    1. /api/user/get-profile-by-slug?url_slug=<后缀>   -> user_id
    2. /api/creator/get-sponsors?user_id=<id>&per_page=50&page=N  -> 赞助者列表

用法：
    python tools/fetch_sponsors.py --slug dudu
    python tools/fetch_sponsors.py --url https://afdian.com/a/dudu
    python tools/fetch_sponsors.py --slug dudu --max 200   # 最多取 200 人

失败时保留旧文件不动，界面继续显示上一次的名单。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests

BASE = "https://afdian.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.core.config import DATA_ROOT  # noqa: E402


class PageDisabled(RuntimeError):
    """创作者主页被停用（最常见的原因是还未实名认证）。"""


def make_session() -> requests.Session:
    s = requests.Session()
    s.trust_env = False          # 绕开本机那个不通的代理
    s.headers.update({"User-Agent": UA, "Referer": BASE + "/"})
    return s


def resolve_user(s: requests.Session, slug: str) -> tuple[str, str, str]:
    """返回 (user_id, 显示名, 主页地址)。"""
    r = s.get(f"{BASE}/api/user/get-profile-by-slug",
              params={"url_slug": slug}, timeout=20)
    d = r.json() if r.text.startswith("{") else {}
    if d.get("ec") != 200:
        raise RuntimeError(f"找不到创作者「{slug}」：{d.get('em') or r.text[:80]}")
    data = d.get("data") or {}
    user = data.get("user") or data
    uid = str(user.get("user_id") or data.get("user_id") or "")
    name = str(user.get("name") or slug)
    if not uid:
        raise RuntimeError(f"接口没返回 user_id，原始响应：{json.dumps(d)[:200]}")
    return uid, name, f"{BASE}/a/{slug}"


def fetch_sponsors(s: requests.Session, uid: str, limit: int) -> list[dict]:
    out: list[dict] = []
    page = 1
    while len(out) < limit and page <= 20:
        r = s.get(f"{BASE}/api/creator/get-sponsors",
                  params={"user_id": uid, "per_page": 50, "page": page}, timeout=25)
        d = r.json() if r.text.startswith("{") else {}
        if d.get("ec") != 200:
            raise RuntimeError(f"拉取赞助者失败：{d.get('em') or r.text[:100]}")
        data = d.get("data") or {}
        items = data.get("list") or []
        em = str(d.get("em") or "").strip()
        if not items:
            # 页面被停用（最常见原因是创作者还没实名认证）时，
            # 不能当成"没有赞助者"——否则会把上一次的正常名单覆盖掉
            if em and ("停用" in em or "不存在" in em):
                raise PageDisabled(em)
            break
        for it in items:
            u = it.get("user") or {}
            name = (u.get("name") or it.get("name") or "").strip()
            if not name:
                continue
            plan = it.get("current_plan") or {}
            months = 0
            try:
                months = int(plan.get("months") or 0)
            except Exception:
                months = 0
            out.append({
                "name": name,
                "avatar": u.get("avatar") or "",
                "months": months,
                "since": str(it.get("create_time") or ""),
            })
        if len(items) < 50:
            break
        page += 1
        time.sleep(0.4)
    return out[:limit]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", default="", help="主页后缀，如 afdian.com/a/dudu 里的 dudu")
    ap.add_argument("--url", default="", help="或直接给主页地址")
    ap.add_argument("--max", type=int, default=200, help="最多抓多少人")
    ap.add_argument("--out", default="", help="输出文件，默认 <data>/sponsors.json")
    ap.add_argument("--exclude", default="",
                    help="排除名单文件（每行一个昵称），默认 <data>/sponsor_exclude.txt")
    args = ap.parse_args()

    slug = args.slug.strip()
    if not slug and args.url:
        m = re.search(r"/a/([^/?#]+)", args.url.strip())
        if m:
            slug = m.group(1)
    if not slug:
        print("请用 --slug 或 --url 指定爱发电主页")
        return 2

    s = make_session()
    uid, name, home = resolve_user(s, slug)
    print(f"创作者：{name}（user_id={uid}）")
    try:
        sponsors = fetch_sponsors(s, uid, args.max)
    except PageDisabled as exc:
        print(f"主页暂不可用：{exc}")
        print("常见原因：创作者尚未完成实名认证（爱发电会隐藏发电榜单）。")
        print("已保留上一次的名单，未做覆盖。")
        return 3
    # 排除名单：爱发电的公开接口只给昵称、不给金额，没法按档位自动筛，
    # 所以留一个手动排除的口子（每行一个昵称，# 开头为注释）。
    ex_path = Path(args.exclude) if args.exclude else (DATA_ROOT / "sponsor_exclude.txt")
    if ex_path.exists():
        names = {ln.strip() for ln in ex_path.read_text(encoding="utf-8").splitlines()
                 if ln.strip() and not ln.strip().startswith("#")}
        if names:
            before = len(sponsors)
            sponsors = [s for s in sponsors if s["name"] not in names]
            print(f"按排除名单去掉 {before - len(sponsors)} 人（共 {len(names)} 条规则）")

    print(f"抓到 {len(sponsors)} 位赞助者")
    if not sponsors:
        print("名单为空——可能是还没有人发电，或创作者关闭了展示。")

    out = Path(args.out) if args.out else (DATA_ROOT / "sponsors.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated": time.strftime("%Y-%m-%d"),
        "source": home,
        "total": len(sponsors),
        "sponsors": sponsors,
    }
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(out)
    print(f"已写入 {out}")
    for sp in sponsors[:5]:
        print(f"  - {sp['name']}" + (f"（{sp['months']} 个月）" if sp["months"] else ""))
    if len(sponsors) > 5:
        print(f"  …共 {len(sponsors)} 人")
    return 0


if __name__ == "__main__":
    sys.exit(main())
