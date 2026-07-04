#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_surf — 「議論の海サーフ」ライブ層ビルダー。

本番 generate.py の入力（原典 src/）が無い環境でも、**コミット済み・検証済みのデータ**だけから
wiki/surf/ を生成する。データ源はすべてリポジトリ内：
  - 会議・議員・議案：wiki/search.json（本番 generate.py が verify 合格後に書き出したもの）
  - 会期：wiki/list.html（本番が書き出した会期パネル）
  - 記事：wiki/articles.py（＋ articles_auto.py）
エッジの導出とページ描画は surf_core に一本化（generate.py と同一ロジック）。

既知の制限：search.json の bills は [:8] 截断。9会議で議案番号を一部取りこぼす（下記 NOTE 参照）。
本番 generate.py 経由では截断前 bills[:30] を surf_core に渡すため、より完全に接続される。

使い方: cd wiki && python3 build_surf.py   → wiki/surf/ に出力
"""
import json, re, html, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import surf_core

WIKI = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(WIKI, "surf")

# ---- 会議（search.json）----
S = json.load(open(os.path.join(WIKI, "search.json"), encoding="utf-8"))
meetings = [{"f": e["f"], "t": e["t"], "c": e["c"], "w": e["w"],
             "members": e.get("m", []), "bills": e.get("b", [])}
            for e in S if e["k"] == "m"]

# ---- 記事（articles.py）----
from articles import ARTICLES as _A
try:
    from articles_auto import ARTICLES_AUTO as _B
except Exception:
    _B = []
articles = _A + _B

# ---- 会期（list.html の会期パネル）----
_lst = open(os.path.join(WIKI, "list.html"), encoding="utf-8").read()
sessions = []
for panel in re.split(r'<section class="panel session-panel', _lst)[1:]:
    name = re.search(r'panel-title">(.*?)</h2>', panel, re.S)
    nm = html.unescape(re.sub(r"<[^>]+>", "", name.group(1)).strip()) if name else "会期"
    files = list(dict.fromkeys(re.findall(r'href="m/([^"]+?\.html)"', panel)))
    if files:
        sessions.append((nm, files))
assert sessions, "list.html から会期を取得できませんでした"

pages, stats, _maps = surf_core.build(
    meetings, articles, sessions,
    note="ベータ",
    caveat="※議案・陳情番号は現行データ源（search.json）の都合で一部の会議で取りこぼしがあります"
           "（機械的制限・順次改善）。")

# ---- 書き出し ----
for d in ("", "m", "p", "b", "c", "s", "a"):
    os.makedirs(os.path.join(OUT, d), exist_ok=True)
for rel, content in pages.items():
    open(os.path.join(OUT, rel), "w", encoding="utf-8").write(content)
open(os.path.join(OUT, "surf.css"), "w", encoding="utf-8").write(surf_core.CSS)

print("WROTE", OUT)
print("stats:", json.dumps(stats, ensure_ascii=False))
print("NOTE: bills are from search.json [:8] (9 meetings truncated). "
      "generate.py path uses full bills[:30].")
