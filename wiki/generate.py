#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gijiroku1 (小金井市議会 非公式会議録) -> editorial knowledge wiki generator.
Reads downloaded source docs in ./src and the index, emits a static wiki into OUT.
Faithful reorganization: reuses existing summaries/structure, no re-summarization.
"""
import re, html, json, os, glob, sys

SRC = "src"
OUT = sys.argv[1] if len(sys.argv) > 1 else "out"
GIJI_BASE = "https://toritarosan.github.io/Gijiroku1"
YT_CHANNEL = "https://www.youtube.com/@koganei_shigikai"

os.makedirs(os.path.join(OUT, "m"), exist_ok=True)
os.makedirs(os.path.join(OUT, "p"), exist_ok=True)

def strip_tags(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s))

def collapse(s):
    return re.sub(r"\s+", " ", s).strip()

# ---- category map from index ----
idx = open("gijiroku_index.html", encoding="utf-8").read()
catmap = {}
for m in re.finditer(r'<a[^>]*href="(R[^"]*\.html)"[^>]*>', idx):
    href = m.group(1); tag = m.group(0)
    cat = re.search(r'data-cat="([^"]*)"', tag)
    catmap[href] = cat.group(1) if cat else "その他"

REIWA0 = 2018  # 令和1 = 2019

def parse_name(fn):
    m = re.match(r"R(\d+)\.(\d+)\.(\d+)_(.+)\.html$", fn)
    if not m:
        return None
    ry, mo, da, rest = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
    rest = rest.replace("_", " ").strip()
    year = REIWA0 + ry
    return {
        "file": fn, "reiwa": ry, "mo": mo, "da": da,
        "iso": f"{year:04d}-{mo:02d}-{da:02d}",
        "wareki": f"令和{ry}年{mo}月{da}日",
        "type": rest,
        "sortkey": (year, mo, da),
    }

def session_label(meta):
    # rough 会期 grouping by month clusters
    y, mo = meta["sortkey"][0], meta["mo"]
    if mo in (2, 3): return f"令和{meta['reiwa']}年 第1回定例会ほか（{mo}月）"
    if mo in (6,): return f"令和{meta['reiwa']}年 第2回定例会（6月）"
    if mo in (9, 10): return f"令和{meta['reiwa']}年 第3回定例会（{mo}月）"
    if mo in (12,): return f"令和{meta['reiwa']}年 第4回定例会（12月）"
    return f"令和{meta['reiwa']}年（{mo}月）"

def get_body(s):
    m = re.search(r"<body[^>]*>(.*)</body>", s, re.S)
    return m.group(1) if m else s

def extract(fn):
    s = open(os.path.join(SRC, fn), encoding="utf-8").read()
    body = get_body(s)
    meta = parse_name(fn)
    meta["cat"] = catmap.get(fn, "その他")
    # videos (embed ids, ordered, unique)
    ids = list(dict.fromkeys(re.findall(r"youtube\.com/embed/([A-Za-z0-9_-]{6,})", s)))
    meta["videos"] = ids
    # timestamped jump links count
    meta["jumps"] = len(re.findall(r"watch\?v=[A-Za-z0-9_-]{6,}&(?:amp;)?t=\d+", s))
    # overview (<details> first <p> or first paragraph)
    ov = ""
    d = re.search(r"<details[^>]*>(.*?)</details>", body, re.S)
    if d:
        p = re.search(r"<p[^>]*>(.*?)</p>", d.group(1), re.S)
        if p: ov = collapse(strip_tags(p.group(1)))
    meta["overview"] = ov
    # h2 sections
    h2list = [collapse(strip_tags(x)) for x in re.findall(r"<h2[^>]*>(.*?)</h2>", body, re.S)]
    # summary HTML block: capture content of a summary-type h2 up to next h2
    summary_html = ""
    for m in re.finditer(r"<h2[^>]*>(.*?)</h2>(.*?)(?=<h2|\Z)", body, re.S):
        title = collapse(strip_tags(m.group(1)))
        if any(k in title for k in ("要約", "一覧", "提出議案", "一般質問", "調査項目")):
            summary_html += f"<h2 class='sec'>{html.escape(title)}</h2>\n" + clean_block(m.group(2))
    meta["summary_html"] = summary_html
    meta["has_summary"] = bool(summary_html)
    # members (h3 that look like names)
    h3list = [collapse(strip_tags(x)) for x in re.findall(r"<h3[^>]*>(.*?)</h3>", body, re.S)]
    members = []
    for h in h3list:
        mm = re.match(r"^(?:\d+番[：:\s　]*)?(.+?)\s*議員$", h)
        if mm:
            nm = re.sub(r"[\s　]+", "", mm.group(1)).strip()
            if 2 <= len(nm) <= 10:
                members.append(nm)
    meta["members"] = list(dict.fromkeys(members))
    # bills
    bills = []
    for h in h3list + h2list:
        if re.match(r"^(議案|意見書案|陳情|請願|認定?第|議員提出|発議)", h):
            bills.append(h)
    for li in re.findall(r"<li[^>]*>(.*?)</li>", body, re.S):
        t = collapse(strip_tags(li))
        if re.match(r"^(議案第|意見書案第|陳情第|請願第)", t):
            bills.append(t)
    meta["bills"] = list(dict.fromkeys(bills))[:30]
    # search snippet
    plain = collapse(strip_tags(body))
    plain = re.sub(r"(動画\s*\d+:\d+\s*再生|一覧に戻る|AIによる文字起こし・自動校正データ)", "", plain)
    meta["snippet"] = plain[:1400]
    return meta

def clean_block(h):
    # keep simple structural tags, drop scripts/styles/iframes/yt buttons & inline styles
    h = re.sub(r"<(script|style|iframe)[^>]*>.*?</\1>", "", h, flags=re.S)
    h = re.sub(r"<a[^>]*class=\"yt-btn\"[^>]*>.*?</a>", "", h, flags=re.S)
    h = re.sub(r"<a[^>]*>(\s*動画[^<]*再生\s*)</a>", "", h, flags=re.S)
    h = re.sub(r"<div[^>]*>\s*</div>", "", h, flags=re.S)
    h = re.sub(r"\sstyle=\"[^\"]*\"", "", h)
    h = re.sub(r"\sclass=\"[^\"]*\"", "", h)
    # demote h2 inside to h3, h3->h4 not needed; keep ul/li/p/strong/h3/h4
    return h

# ---- run extraction ----
docs = [extract(os.path.basename(f)) for f in glob.glob(os.path.join(SRC, "*.html"))]
docs = [d for d in docs if d]
docs.sort(key=lambda d: d["sortkey"], reverse=True)
print("parsed docs:", len(docs))
print("with summary:", sum(d["has_summary"] for d in docs))
print("total videos:", sum(len(d["videos"]) for d in docs))

# member -> appearances
people = {}
for d in docs:
    for mem in d["members"]:
        people.setdefault(mem, []).append(d)

# ---------- HTML templates ----------
def page(title, body, depth=0):
    rel = "../" * depth
    return f"""<!DOCTYPE html>
<html lang="ja"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<link rel="stylesheet" href="{rel}style.css">
</head><body>
{body}
<script src="{rel}video.js"></script>
</body></html>
"""

def video_buttons(d, depth):
    if not d["videos"]:
        return ""
    btns = []
    for i, vid in enumerate(d["videos"], 1):
        btns.append(f'<button class="watch" data-yt="{vid}" data-title="{html.escape(d["type"]+" "+d["wareki"])}（動画{i}）">動画{i}を見る</button>')
    note = f'<span class="vidnote">YouTube {len(d["videos"])}本・頭出しリンク {d["jumps"]}か所</span>' if d["jumps"] else ""
    return '<div class="videorow">' + " ".join(btns) + note + "</div>"

def mfile(d):  # meeting page filename
    return d["file"]

def meeting_page(d):
    depth = 1
    crumb = f'<div class="crumb"><a href="../index.html">ホーム</a> › {html.escape(d["cat"])} › {html.escape(d["wareki"])}</div>'
    badges = ""
    chips = f'<div class="chips"><span class="chip">{html.escape(d["cat"])}</span><span class="chip tag">{html.escape(d["iso"])}</span>'
    if d["has_summary"]:
        chips += '<span class="chip">要約あり</span>'
    chips += "</div>"
    # members
    memhtml = ""
    if d["members"]:
        links = " ".join(f'<a class="chip" href="../p/{enc(m)}.html">{html.escape(m)}</a>' for m in d["members"])
        memhtml = f'<h2 class="sec">登壇した議員</h2><div class="chips">{links}</div>'
    # bills
    billhtml = ""
    if d["bills"]:
        items = "".join(f"<li>{html.escape(b)}</li>" for b in d["bills"])
        billhtml = f'<h2 class="sec">議案・案件</h2><ul class="clean">{items}</ul>'
    # summary or note
    if d["summary_html"]:
        content = d["summary_html"]
    else:
        content = (f'<h2 class="sec">この会議について</h2>'
                   f'<p class="body">{html.escape(d["overview"]) if d["overview"] else "この会議録は全文の文字起こしと録画で構成されています。要点の要約は下記の原典でご確認ください。"}</p>')
    body = f"""
<div class="topbar"><div class="wrap">
  <a class="logo" href="../index.html">Koganei Council Wiki</a>
  <input class="search" id="q" placeholder="検索（トップへ）" onfocus="location.href='../index.html'">
</div></div>
<div class="wrap">
  {crumb}
  <div class="ai-banner"><span><b>原典はAIによる文字起こし・自動校正データです。</b>本ページはそれを再編集した非公式Wikiで、要約や抽出に誤りを含む場合があります。正確な内容は原典・録画でご確認ください。</span></div>
  <div class="card">
    <p class="subtitle">{html.escape(d["cat"])} ／ {html.escape(d["wareki"])}</p>
    <h1 class="title">{html.escape(d["type"])}</h1>
    {chips}
    {video_buttons(d, depth)}
    {content}
    {memhtml}
    {billhtml}
    <h2 class="sec">原典（全文・動画つき）</h2>
    <p class="src">この会議の全文文字起こしと録画は原典でご覧いただけます。<br>
      原典：<a href="{GIJI_BASE}/{enc(d['file'])}" target="_blank" rel="noopener">{html.escape(d['file'])} ↗</a></p>
  </div>
  <div class="footer"><b>KOGANEI COUNCIL WIKI</b> — 原典：小金井市議会 非公式会議録（Gijiroku1）</div>
</div>
"""
    return page(f"{d['type']} {d['wareki']}｜小金井市議会Wiki", body, depth=1)

def enc(name):
    return name  # keep Japanese; browsers/Pages handle it. Links use encodeURI in JS where needed.

def person_page(name, appearances):
    apps = sorted(appearances, key=lambda d: d["sortkey"], reverse=True)
    rows = "".join(
        f'<tr><td>{html.escape(d["wareki"])}</td><td>{html.escape(d["cat"])}</td>'
        f'<td><a href="../m/{enc(d["file"])}">{html.escape(d["type"])}</a></td></tr>'
        for d in apps)
    body = f"""
<div class="topbar"><div class="wrap">
  <a class="logo" href="../index.html">Koganei Council Wiki</a>
  <input class="search" placeholder="検索（トップへ）" onfocus="location.href='../index.html'">
</div></div>
<div class="wrap">
  <div class="crumb"><a href="../index.html">ホーム</a> › 議員 › {html.escape(name)}</div>
  <div class="ai-banner"><span><b>自動生成された議員ページ。</b>登壇記録は会議録の見出しから抽出したもので、抜けがある場合があります。</span></div>
  <div class="card">
    <p class="subtitle">議員プロフィール（登壇記録）</p>
    <h1 class="title">{html.escape(name)} 議員</h1>
    <div class="chips"><span class="chip">登壇 {len(apps)} 会議</span></div>
    <h2 class="sec">登壇した会議</h2>
    <table><tr><th>日付</th><th>区分</th><th>会議</th></tr>{rows}</table>
  </div>
  <div class="footer"><b>KOGANEI COUNCIL WIKI</b> — 原典：小金井市議会 非公式会議録（Gijiroku1）</div>
</div>
"""
    return page(f"{name} 議員｜小金井市議会Wiki", body, depth=1)

# ---- write meeting pages ----
for d in docs:
    open(os.path.join(OUT, "m", d["file"]), "w", encoding="utf-8").write(meeting_page(d))
# ---- write person pages ----
for name, apps in people.items():
    open(os.path.join(OUT, "p", name + ".html"), "w", encoding="utf-8").write(person_page(name, apps))

# ---- search index ----
search = [{
    "f": d["file"], "t": d["type"], "c": d["cat"], "d": d["iso"], "w": d["wareki"],
    "m": d["members"], "b": d["bills"][:8], "s": d["snippet"][:500], "v": len(d["videos"])
} for d in docs]
json.dump(search, open(os.path.join(OUT, "search.json"), "w", encoding="utf-8"), ensure_ascii=False)

# ---- index page ----
cats = ["本会議", "常任委員会", "予算特別委員会", "議会運営委員会", "特別委員会・協議会"]
catcount = {c: sum(1 for d in docs if d["cat"] == c) for c in cats}
# group by session
from collections import OrderedDict
groups = OrderedDict()
for d in docs:
    groups.setdefault(session_label(d), []).append(d)
people_sorted = sorted(people.items(), key=lambda kv: -len(kv[1]))
people_chips = " ".join(
    f'<a class="chip" href="p/{enc(n)}.html">{html.escape(n)} <span class="ct">{len(a)}</span></a>'
    for n, a in people_sorted)
catfilter = '<button class="filt active" data-c="all">すべて</button>' + "".join(
    f'<button class="filt" data-c="{html.escape(c)}">{html.escape(c)} <span class="ct">{catcount[c]}</span></button>'
    for c in cats)

index_body = f"""
<div class="wrap">
  <header class="masthead">
    <div class="kicker">Auto-generated from official-record archive</div>
    <a class="logo" href="index.html">Koganei&nbsp;Council&nbsp;Wiki</a>
    <div class="jp">小金井市議会 ナレッジ</div>
  </header>
  <hr class="rule-double">
  <div class="dateline"><span>収録 {len(docs)} 会議</span><span>動画 {sum(len(d['videos']) for d in docs)} 本</span><span>原典：非公式会議録</span></div>
  <hr class="rule-thin">
  <div class="ai-banner"><span><b>本誌は小金井市議会の非公式会議録（AI文字起こし）を再編集した検索Wikiです。</b>要約・抽出はAIによるもので誤りを含む場合があります。正確な内容は各ページの原典・録画でご確認ください。</span></div>

  <div style="margin:22px 0">
    <input id="q" class="bigsearch" placeholder="🔍 会議・議員・議案・キーワードで検索（例：補正予算、空調、岸田、虐待）" autocomplete="off">
    <div class="filters">{catfilter}</div>
  </div>

  <div id="results"></div>

  <h2 class="sec">会期・日付順</h2>
  <div id="browse">
"""
for label, ds in groups.items():
    index_body += f'<h3 class="grp">{html.escape(label)}</h3><div class="grid">'
    for d in ds:
        sub = (d["bills"][0] if d["bills"] else (d["members"] and ("一般質問：" + "・".join(d["members"][:4]) + ("ほか" if len(d["members"])>4 else "")) ) or d["overview"][:70] or "全文・録画あり")
        index_body += (f'<a class="tile" data-c="{html.escape(d["cat"])}" href="m/{enc(d["file"])}">'
                       f'<span class="num">{html.escape(d["iso"])}</span>'
                       f'<h3>{html.escape(d["type"])}</h3>'
                       f'<p>{html.escape(str(sub)[:78])}</p>'
                       f'<span class="meta">{html.escape(d["cat"])} ・ 動画{len(d["videos"])}本</span></a>')
    index_body += '</div>'
index_body += f"""
  </div>

  <h2 class="sec">議員から探す</h2>
  <div class="chips people">{people_chips}</div>

  <div class="footer">
    <b>KOGANEI COUNCIL WIKI</b> — LLM editorial reorganization<br>
    原典：<a href="{GIJI_BASE}/" target="_blank" rel="noopener">小金井市議会 非公式会議録</a> ／
    <a href="{YT_CHANNEL}" target="_blank" rel="noopener">YouTubeチャンネル</a> ／ 分類・要約はAIによる自動生成
  </div>
</div>
<script src="app.js"></script>
"""
open(os.path.join(OUT, "index.html"), "w", encoding="utf-8").write(page("KOGANEI COUNCIL WIKI｜小金井市議会ナレッジ", index_body))

print("WROTE:", OUT)
print(" meeting pages:", len(docs), "| person pages:", len(people))
