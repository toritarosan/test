#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_one.py — 単一ドラフトファイルを原典突合で検証する（ドラフト作成エージェント用）

使い方:
    python3 verify_one.py drafts/wf_<slug>.py

ドラフトファイルは ARTICLES_DRAFT = [dict(...), ...] を定義していること。
各 dict の src=[原典ファイル名] を src/ から読み込み、verify.py で照合する。
ERROR が1件でもあれば終了コード1、なければ0。warning は表示のみ。
"""
import re, os, sys, html
import verify as V

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
REIWA0 = 2018

def load_source(fn):
    p = os.path.join(SRC, fn)
    if not os.path.exists(p):
        return None
    s = open(p, encoding="utf-8").read()
    b = re.search(r"<body[^>]*>(.*)</body>", s, re.S)
    return V.strip_tags(b.group(1) if b else s)

def meta_whitelist(fn):
    m = re.match(r"R(\d+)\.(\d+)\.(\d+)_", fn)
    if not m:
        return set()
    ry, mo, da = int(m.group(1)), int(m.group(2)), int(m.group(3))
    y = REIWA0 + ry
    return {f"{y:04d}-{mo:02d}-{da:02d}", f"{y}/{mo:02d}/{da:02d}",
            f"令和{ry}年{mo}月{da}日", f"{mo}.{da}", f"{mo}月{da}日", f"令和{ry}年", str(y)}

REQUIRED = {"slug", "cat", "date", "wareki", "src", "video", "people", "tags", "title", "lead", "body"}

def main():
    if len(sys.argv) < 2:
        print("usage: python3 verify_one.py <draftfile>"); sys.exit(2)
    path = sys.argv[1]
    ns = {}
    try:
        exec(open(path, encoding="utf-8").read(), ns)
    except Exception as e:
        print(f"[構文エラー] {path}: {e}"); sys.exit(1)
    arts = ns.get("ARTICLES_DRAFT")
    if not arts:
        print("ARTICLES_DRAFT が空、または未定義です"); sys.exit(1)

    total_err = 0
    for a in arts:
        miss = REQUIRED - set(a)
        if miss:
            print(f"[ERROR] {a.get('slug','?')}: 必須キー欠損 {miss}"); total_err += 1; continue
        srcs = []
        bad_src = False
        for f in a["src"]:
            t = load_source(f)
            if t is None:
                print(f"[ERROR] {a['slug']}: src ファイルが src/ に存在しない: {f}")
                total_err += 1; bad_src = True
            else:
                srcs.append(t)
        if bad_src:
            continue
        wl = set()
        for f in a["src"]:
            wl |= meta_whitelist(f)
        wl |= {a["date"], a["wareki"], a["date"].replace("-", "/")}
        errs, warns = V.verify_article(a, srcs, wl)
        status = "OK" if not errs else f"ERROR x{len(errs)}"
        print(f"[{status}] {a['slug']}")
        for e in errs:
            print(f"    ERROR: {e}")
        for w in warns:
            print(f"    warn : {w}")
        total_err += len(errs)

    print(f"---- {'合格（ERROR 0）' if total_err == 0 else f'不合格（ERROR {total_err}件）'} ----")
    sys.exit(0 if total_err == 0 else 1)

if __name__ == "__main__":
    main()
