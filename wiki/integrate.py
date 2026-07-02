#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""integrate.py — エージェント下書きを機械検証し、合格した記事のみ articles_auto.py に採用する"""
import re, glob, os, sys, pprint
import verify as V

SRC = "src"
def load_source(fn):
    s = open(os.path.join(SRC, fn), encoding="utf-8").read()
    b = re.search(r"<body[^>]*>(.*)</body>", s, re.S)
    return V.strip_tags(b.group(1) if b else s)

REIWA0 = 2018
def meta_whitelist(fn):
    m = re.match(r"R(\d+)\.(\d+)\.(\d+)_", fn)
    if not m: return set()
    ry, mo, da = int(m.group(1)), int(m.group(2)), int(m.group(3))
    y = REIWA0 + ry
    return {f"{y:04d}-{mo:02d}-{da:02d}", f"{y}/{mo:02d}/{da:02d}",
            f"令和{ry}年{mo}月{da}日", f"{mo}.{da}", f"{mo}月{da}日", f"令和{ry}年", str(y)}

REQUIRED = {"slug","cat","date","wareki","src","video","people","tags","title","lead","body"}
passed, failed = [], []
for path in sorted(glob.glob("drafts/agent*.py")) + sorted(glob.glob("drafts/wf_*.py")):
    ns = {}
    try:
        exec(open(path, encoding="utf-8").read(), ns)
    except Exception as e:
        print(f"[構文エラー] {path}: {e}"); continue
    for a in ns.get("ARTICLES_DRAFT", []):
        miss = REQUIRED - set(a)
        if miss:
            failed.append((a.get("slug","?"), [f"欠損キー: {miss}"])); continue
        srcs = [load_source(f) for f in a["src"] if os.path.exists(os.path.join(SRC, f))]
        if len(srcs) != len(a["src"]):
            failed.append((a["slug"], ["src ファイルが存在しない"])); continue
        wl = set()
        for f in a["src"]: wl |= meta_whitelist(f)
        wl |= {a["date"], a["wareki"], a["date"].replace("-", "/")}
        errs, warns = V.verify_article(a, srcs, wl)
        if errs:
            failed.append((a["slug"], errs))
        else:
            passed.append(a)
            for w in warns: print(f"  warn {a['slug']}: {w}")

print(f"\n==== 合格 {len(passed)} / 不合格 {len(failed)} ====")
for slug, errs in failed:
    print(f"\n[不合格] {slug}")
    for e in errs: print(f"   {e}")

with open("articles_auto.py", "w", encoding="utf-8") as f:
    f.write('#!/usr/bin/env python3\n# -*- coding: utf-8 -*-\n')
    f.write('"""機械検証（verify.py）合格済みの自動生成記事。integrate.py により生成。手動編集しない。"""\n\n')
    f.write("ARTICLES_AUTO = ")
    f.write(pprint.pformat(passed, width=120, sort_dicts=False))
    f.write("\n")
print(f"\narticles_auto.py に {len(passed)} 記事を書き出しました")
