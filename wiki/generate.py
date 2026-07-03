#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gijiroku1（小金井市議会 非公式会議録）→ 会議録アーカイブ 生成スクリプト
デザイン：Gijiroku1 最新ポータル準拠（緑×クリーム×コーラル、角丸2px）
入力：./src/*.html（原典62本）+ ./gijiroku_index.html + articles.py
出力：OUT/（index.html, list.html, m/×62, p/×N, a/×記事, search.json）
方針：原典の要約・構造を忠実に再利用（再要約しない）。
"""
import re, html, json, os, glob, sys
from articles import ARTICLES
try:
    from articles_auto import ARTICLES_AUTO
    ARTICLES = ARTICLES + ARTICLES_AUTO
except ImportError:
    pass
import verify as V

SRC = "src"
OUT = sys.argv[1] if len(sys.argv) > 1 else "out"
GIJI = "https://toritarosan.github.io/Gijiroku1"
YT_CH = "https://www.youtube.com/@koganei_shigikai"
KENSAKU = "https://www.city.koganei.tokyo.dbsr.jp/"

for d in ("m", "p", "a"):
    os.makedirs(os.path.join(OUT, d), exist_ok=True)

def strip_tags(s): return html.unescape(re.sub(r"<[^>]+>", "", s))
def collapse(s): return re.sub(r"\s+", " ", s).strip()
def esc(s): return html.escape(str(s))

# ---------- カテゴリ色（原典 list.html と同一のドット色） ----------
DOT = {"all":"#0017c1","本会議":"#ce0000","予算特別委員会":"#e25100","常任委員会":"#264af4",
       "議会運営委員会":"#6f23d0","特別委員会・協議会":"#1d8b56"}
def catpill(cat):
    return (f'<span class="cat-pill"><span class="cdot" style="background:{DOT.get(cat,"#767676")};"></span>'
            f'{esc(cat)}</span>')
def kind(cat):
    return (f'<span class="kind"><span class="cdot" style="background:{DOT.get(cat,"#767676")};"></span>'
            f'{esc(cat)}</span>')

# ---------- 原典 index：カテゴリ & 会期 ----------
idx = open("gijiroku_index.html", encoding="utf-8").read()
lst = open("gijiroku_list.html", encoding="utf-8").read()
catmap, sessions = {}, []
for m in re.finditer(r'<(?:a|button)[^>]*data-href="(R[^"]*\.html)"[^>]*>|<a[^>]*href="(R[^"]*\.html)"[^>]*>', lst):
    pass
for m in re.finditer(r'<button class="entry" data-cat="([^"]*)" data-href="(R[^"]*\.html)"', lst):
    catmap[m.group(2)] = m.group(1)
for m in re.finditer(r'<details class="session"[^>]*>(.*?)</details>', lst, re.S):
    blk = m.group(1)
    name = collapse(strip_tags(re.search(r'<span class="session-name">(.*?)</span>', blk).group(1)))
    files = re.findall(r'data-href="(R[^"]*\.html)"', blk)
    sessions.append((name, files))
assert sum(len(f) for _, f in sessions) >= 60, "session parse failed"

REIWA0 = 2018
def parse_name(fn):
    m = re.match(r"R(\d+)\.(\d+)\.(\d+)_(.+)\.html$", fn)
    if not m: return None
    ry, mo, da, rest = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
    return {"file": fn, "reiwa": ry, "mo": mo, "da": da,
            "iso": f"{REIWA0+ry:04d}-{mo:02d}-{da:02d}",
            "slash": f"{REIWA0+ry}/{mo:02d}/{da:02d}",
            "wareki": f"令和{ry}年{mo}月{da}日", "md": f"{mo}.{da}",
            "type": rest.replace("_", " ").strip(), "sortkey": (REIWA0+ry, mo, da)}

def clean_block(h):
    h = re.sub(r"<(script|style|iframe)[^>]*>.*?</\1>", "", h, flags=re.S)
    h = re.sub(r'<a[^>]*class="yt-btn"[^>]*>.*?</a>', "", h, flags=re.S)
    h = re.sub(r"<a[^>]*>(\s*動画[^<]*再生\s*)</a>", "", h, flags=re.S)
    h = re.sub(r"<div[^>]*>\s*</div>", "", h, flags=re.S)
    h = re.sub(r'\sstyle="[^"]*"', "", h)
    h = re.sub(r'\sclass="[^"]*"', "", h)
    return h

def extract(fn):
    s = open(os.path.join(SRC, fn), encoding="utf-8").read()
    b = re.search(r"<body[^>]*>(.*)</body>", s, re.S)
    body = b.group(1) if b else s
    meta = parse_name(fn)
    meta["cat"] = catmap.get(fn, "その他")
    meta["videos"] = list(dict.fromkeys(re.findall(r"youtube\.com/embed/([A-Za-z0-9_-]{6,})", s)))
    meta["jumps"] = len(re.findall(r"watch\?v=[A-Za-z0-9_-]{6,}&(?:amp;)?t=\d+", s))
    ov = ""
    d = re.search(r"<details[^>]*>(.*?)</details>", body, re.S)
    if d:
        p = re.search(r"<p[^>]*>(.*?)</p>", d.group(1), re.S)
        if p: ov = collapse(strip_tags(p.group(1)))
    meta["overview"] = ov
    summary_html = ""
    for m in re.finditer(r"<h2[^>]*>(.*?)</h2>(.*?)(?=<h2|\Z)", body, re.S):
        t = collapse(strip_tags(m.group(1)))
        if any(k in t for k in ("要約", "一覧", "提出議案", "一般質問", "調査項目")):
            summary_html += f"<h2 class='sec'>{esc(t)}</h2>\n" + clean_block(m.group(2))
    meta["summary_html"] = summary_html
    meta["has_summary"] = bool(summary_html)
    h3list = [collapse(strip_tags(x)) for x in re.findall(r"<h3[^>]*>(.*?)</h3>", body, re.S)]
    members = []
    for h in h3list:
        mm = re.match(r"^(?:\d+番[：:\s　]*)?(.+?)\s*議員$", h)
        if mm:
            nm = re.sub(r"[\s　]+", "", mm.group(1)).strip()
            if 2 <= len(nm) <= 10: members.append(nm)
    meta["members"] = list(dict.fromkeys(members))
    bills = []
    h2list = [collapse(strip_tags(x)) for x in re.findall(r"<h2[^>]*>(.*?)</h2>", body, re.S)]
    for h in h3list + h2list:
        if re.match(r"^(議案|意見書案|陳情|請願|認定?第|議員提出|発議)", h): bills.append(h)
    for li in re.findall(r"<li[^>]*>(.*?)</li>", body, re.S):
        t = collapse(strip_tags(li))
        if re.match(r"^(議案第|意見書案第|陳情第|請願第)", t): bills.append(t)
    meta["bills"] = list(dict.fromkeys(bills))[:30]
    plain = collapse(strip_tags(body))
    plain = re.sub(r"(動画\s*\d+:\d+\s*再生|一覧に戻る|AIによる文字起こし・自動校正データ)", "", plain)
    meta["snippet"] = plain[:1400]
    return meta

docs = {d["file"]: d for f in glob.glob(os.path.join(SRC, "*.html"))
        if (d := extract(os.path.basename(f)))}
print("parsed:", len(docs), "| with summary:", sum(d["has_summary"] for d in docs.values()),
      "| videos:", sum(len(d["videos"]) for d in docs.values()))

people = {}
for d in docs.values():
    for mem in d["members"]:
        people.setdefault(mem, []).append(d)

# =========================================================
# 共通部品
# =========================================================
FOOTNOTE = ("本サイトは非公式のAI生成コンテンツです。データの更新状況やAIの精度には限界があります。"
            "内容の正確性・最新性については原典・公式情報をご確認ください。")

def site_footer(depth=0):
    rel = "../" * depth
    return f"""<footer class="site-footer"><div class="container inner">
  <p class="footer-note">{FOOTNOTE}</p>
  <div class="footer-links">
    <a href="{rel}index.html">ホーム</a>
    <a href="{rel}list.html">会議一覧</a>
    <a href="{GIJI}/" target="_blank" rel="noopener">原典サイト ↗</a>
    <a href="{KENSAKU}" target="_blank" rel="noopener">公式会議録 ↗</a>
  </div>
</div></footer>"""

def sitenav(depth=1, active=""):
    rel = "../" * depth
    def cls(k): return ' class="active"' if k == active else ""
    return f"""<nav class="sitenav" aria-label="サイト共通ナビ"><div class="sitenav-in">
  <a class="sitenav-brand" href="{rel}index.html"><img src="{rel}logo.png" alt="">会議録アーカイブ</a>
  <div class="sitenav-links">
    <a href="{rel}index.html">ホーム</a>
    <a href="{rel}list.html">会議一覧</a>
    <a href="{rel}index.html#articles">議題まとめ</a>
    <a href="{GIJI}/" target="_blank" rel="noopener">原典サイト<span class="ext">↗</span></a>
    <a href="{YT_CH}" target="_blank" rel="noopener">原典動画<span class="ext">↗</span></a>
  </div>
</div></nav>"""

EMBED_JS = ("<script>try{if(window.self!==window.top)document.documentElement.classList.add('embedded');}"
            "catch(e){document.documentElement.classList.add('embedded');}</script>")
PROG_JS = """<script>
(function(){var p=document.querySelector('.prog');if(!p)return;
addEventListener('scroll',function(){var h=document.documentElement;
var m=h.scrollHeight-h.clientHeight;p.style.width=(m>0?(h.scrollTop/m*100):0)+'%';},{passive:true});})();
</script>"""

def shell(title, body, depth=0, docpage=False):
    rel = "../" * depth
    cls = ' class="docpage"' if docpage else ""
    return f"""<!DOCTYPE html>
<html lang="ja"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<link rel="icon" href="{rel}logo.png">
<link rel="stylesheet" href="{rel}style.css">
</head><body{cls}>
{EMBED_JS}
{body}
{PROG_JS}
<script src="{rel}video.js"></script>
</body></html>
"""

BANNER = ('<div class="ai-banner"><span><b>非公式・AI生成コンテンツ。</b>'
          '原典（AI文字起こし）をもとに自動編集・再構成したものです。要約・抽出に誤りを含む場合があります。'
          '正確な内容は原典・録画・公式会議録でご確認ください。</span></div>')

def status_badge(d):
    return ('<span class="badge official">要約つき</span>' if d["has_summary"]
            else '<span class="badge sokuho">文字起こし</span>')

def video_buttons(vids, label, jumps=0):
    if not vids: return ""
    btns = " ".join(f'<button class="watch" data-yt="{v}" data-title="{esc(label)}（動画{i}）">動画{i}を見る</button>'
                    for i, v in enumerate(vids, 1))
    note = f'<span class="vidnote">YouTube {len(vids)}本' + (f'・原典に頭出し {jumps}か所' if jumps else "") + "</span>"
    return f'<div class="videorow">{btns}{note}</div>'

# =========================================================
# 会議ページ
# =========================================================
def meeting_page(d):
    memhtml = ""
    if d["members"]:
        links = " ".join(f'<a class="chip" href="../p/{m}.html">{esc(m)}</a>' for m in d["members"])
        memhtml = f'<h2 class="sec">登壇した議員</h2><div class="chips">{links}</div>'
    billhtml = ""
    if d["bills"]:
        items = "".join(f"<li>{esc(b)}</li>" for b in d["bills"])
        billhtml = f'<h2 class="sec">議案・案件</h2><ul>{items}</ul>'
    if d["summary_html"]:
        content = f'<div class="sum"><p class="lab">AI要約</p>{d["summary_html"]}</div>'
    else:
        note = esc(d["overview"]) if d["overview"] else "この会議録は全文の文字起こしと録画で構成されています。詳細は原典でご確認ください。"
        content = f'<h2 class="sec">この会議について</h2><p>{note}</p>'
    body = f"""{sitenav(1)}
<div class="prog"></div>
<div class="docwrap">
  <div class="top-eyebrow"><span class="sq"></span><a href="../index.html">ホーム</a><span>›</span><a href="../list.html">会議一覧</a><span>›</span><span>{esc(d["wareki"])}</span></div>
  <div class="dochero">
    <p class="date">{esc(d["slash"])} {catpill(d["cat"])} {status_badge(d)}</p>
    <h1>{esc(d["type"])}</h1>
    <span class="srcline">原典：<a href="{GIJI}/{d['file']}" target="_blank" rel="noopener">{esc(d['file'])} ↗</a>（全文・発言ごとの動画頭出しつき）</span>
  </div>
  {BANNER}
  {video_buttons(d["videos"], d["type"] + " " + d["wareki"], d["jumps"])}
  {content}
  {memhtml}
  {billhtml}
  <p class="src">出典：小金井市議会 非公式会議録（作成：ながとり太郎議員）／
    <a href="{GIJI}/{d['file']}" target="_blank" rel="noopener">この会議の原典を開く ↗</a>・
    <a href="{YT_CH}" target="_blank" rel="noopener">市議会YouTube ↗</a></p>
</div>
{site_footer(1)}
"""
    return shell(f"{d['type']} {d['wareki']}｜会議録アーカイブ（非公式）", body, depth=1, docpage=True)

# =========================================================
# 議員ページ
# =========================================================
def person_page(name, apps):
    apps = sorted(apps, key=lambda d: d["sortkey"], reverse=True)
    rows = "".join(
        f'<tr><td><span class="date">{esc(d["slash"])}</span></td><td>{kind(d["cat"])}</td>'
        f'<td><a class="meeting-link" href="../m/{d["file"]}">{esc(d["type"])}</a></td>'
        f'<td>{status_badge(d)}</td></tr>' for d in apps)
    arts = [a for a in ARTICLES if name in a["people"]]
    arthtml = ""
    if arts:
        items = "".join(f'<li><a href="../a/{a["slug"]}.html">{esc(a["title"])}</a></li>' for a in arts)
        arthtml = f'<h2 class="sec">関連する議題まとめ</h2><ul>{items}</ul>'
    body = f"""{sitenav(1)}
<div class="prog"></div>
<div class="docwrap">
  <div class="top-eyebrow"><span class="sq"></span><a href="../index.html">ホーム</a><span>›</span><span>議員</span><span>›</span><span>{esc(name)}</span></div>
  <div class="dochero">
    <p class="date">議員ページ（登壇記録の自動集約）</p>
    <h1>{esc(name)} 議員</h1>
  </div>
  {BANNER}
  {arthtml}
  <h2 class="sec">登壇した会議（{len(apps)}件）</h2>
  <table><tr><th>日付</th><th>種別</th><th>会議</th><th>状態</th></tr>{rows}</table>
  <p class="src">登壇記録は会議録の見出しから自動抽出したもので、抜けがある場合があります。</p>
</div>
{site_footer(1)}
"""
    return shell(f"{name} 議員｜会議録アーカイブ（非公式）", body, depth=1, docpage=True)

# =========================================================
# 議題まとめページ
# =========================================================
def article_page(a):
    srcs = "".join(
        f'<li><a href="../m/{f}">{esc(docs[f]["type"])}（{esc(docs[f]["wareki"])}）</a> ／ '
        f'<a href="{GIJI}/{f}" target="_blank" rel="noopener">原典 ↗</a></li>'
        for f in a["src"] if f in docs)
    ppl = " ".join(f'<a class="chip" href="../p/{p}.html">{esc(p)}</a>' for p in a["people"])
    tags = " ".join(f'<span class="chip">#{esc(t)}</span>' for t in a["tags"])
    others = [x for x in ARTICLES if x["slug"] != a["slug"]][:3]
    rel = "".join(f'<li><a href="{x["slug"]}.html">{esc(x["title"])}</a></li>' for x in others)
    body = f"""{sitenav(1)}
<div class="prog"></div>
<div class="docwrap">
  <div class="top-eyebrow"><span class="sq"></span><a href="../index.html">ホーム</a><span>›</span><span>議題まとめ</span></div>
  <div class="dochero">
    <p class="date">{esc(a["wareki"])} {catpill(a["cat"])} <span class="badge sokuho">議題まとめ</span></p>
    <h1>{esc(a["title"])}</h1>
    <p class="lead">{esc(a["lead"])}</p>
  </div>
  {BANNER}
  <div class="videorow"><button class="watch" data-yt="{a["video"]}" data-title="{esc(a["title"])}">この会議の録画を見る</button></div>
  {a["body"]}
  <h2 class="sec">関係する議員</h2><div class="chips">{ppl}</div>
  <div class="chips">{tags}</div>
  <h2 class="sec">出典となった会議</h2><ul>{srcs}</ul>
  <h2 class="sec">ほかの議題まとめ</h2><ul>{rel}</ul>
  <p class="src">本記事は原典の要約データを再構成したものです。数値・固有名詞・引用は原典との機械照合（verify.py）を通過しています。発言の正確な文脈は原典・録画でご確認ください。</p>
</div>
{site_footer(1)}
"""
    return shell(f"{a['title']}｜会議録アーカイブ（非公式）", body, depth=1, docpage=True)

# ---------- 記事の機械検証（原典突合）：不合格なら中止 ----------
def _load_source(fn):
    s = open(os.path.join(SRC, fn), encoding="utf-8").read()
    b = re.search(r"<body[^>]*>(.*)</body>", s, re.S)
    return V.strip_tags(b.group(1) if b else s)

def _meta_whitelist(fn):
    d = parse_name(fn)
    if not d: return set()
    return {d["iso"], d["slash"], d["wareki"], d["md"],
            f'{d["mo"]}月{d["da"]}日', f'令和{d["reiwa"]}年', str(d["sortkey"][0])}

_ok, _report = V.verify_all(ARTICLES, _load_source, _meta_whitelist)
open(os.path.join(OUT, "verify_report.txt"), "w", encoding="utf-8").write(_report)
print(_report)
if not _ok:
    sys.exit("記事の機械検証が不合格のため、生成を中止しました（verify_report.txt 参照）")

# ---------- 書き出し ----------
for d in docs.values():
    open(os.path.join(OUT, "m", d["file"]), "w", encoding="utf-8").write(meeting_page(d))
for name, apps in people.items():
    open(os.path.join(OUT, "p", name + ".html"), "w", encoding="utf-8").write(person_page(name, apps))
for a in ARTICLES:
    open(os.path.join(OUT, "a", a["slug"] + ".html"), "w", encoding="utf-8").write(article_page(a))

# ---------- 検索インデックス ----------
search = [{"k": "m", "f": d["file"], "t": d["type"], "c": d["cat"], "d": d["iso"], "w": d["wareki"],
           "m": d["members"], "b": d["bills"][:8], "s": d["snippet"][:500], "v": len(d["videos"]),
           "sm": 1 if d["has_summary"] else 0}
          for d in sorted(docs.values(), key=lambda x: x["sortkey"], reverse=True)]
search += [{"k": "a", "f": a["slug"] + ".html", "t": a["title"], "c": a["cat"], "d": a["date"],
            "w": a["wareki"], "m": a["people"], "b": a["tags"],
            "s": a["lead"] + " " + collapse(strip_tags(a["body"]))[:400], "v": 1, "sm": 1}
           for a in ARTICLES]
json.dump(search, open(os.path.join(OUT, "search.json"), "w", encoding="utf-8"), ensure_ascii=False)

# =========================================================
# ホーム（ポータル）
# =========================================================
CATS = ["本会議", "常任委員会", "予算特別委員会", "議会運営委員会", "特別委員会・協議会"]
catcount = {c: sum(1 for d in docs.values() if d["cat"] == c) for c in CATS}
total_v = sum(len(d["videos"]) for d in docs.values())
all_docs = sorted(docs.values(), key=lambda x: x["sortkey"], reverse=True)
recent = all_docs[:5]

def header_nav(active="home"):
    def cls(k): return ' class="active"' if k == active else ""
    return f"""<header class="site-header"><div class="container inner">
  <a class="brand" href="index.html" aria-label="会議録アーカイブ ホーム">
    <img class="logo" src="logo.png" alt="">
    <span class="brand-text">
      <span class="kicker">小金井市議会</span>
      <h1>会議録アーカイブ <span class="beta">非公式</span></h1>
      <p>原典「非公式会議録」（ながとり太郎議員）のAI再編集・検証済み（読み取り専用）</p>
    </span>
  </a>
  <nav class="nav">
    <a{cls("home")} href="index.html">ホーム</a>
    <a{cls("list")} href="list.html">会議一覧</a>
    <a href="index.html#articles">議題まとめ</a>
    <a href="{GIJI}/" target="_blank" rel="noopener">原典サイト<span class="ext">↗</span></a>
    <a href="{YT_CH}" target="_blank" rel="noopener">原典動画<span class="ext">↗</span></a>
  </nav>
</div></header>"""

acards = "".join(f"""<a class="acard" href="a/{a["slug"]}.html">
  <span class="ameta">{kind(a["cat"])}<span>{esc(a["wareki"])}</span></span>
  <h3>{esc(a["title"])}</h3><p>{esc(a["lead"])}</p></a>""" for a in ARTICLES)

people_sorted = sorted(people.items(), key=lambda kv: -len(kv[1]))
pchips = "".join(f'<a class="pchip" href="p/{n}.html">{esc(n)}<span class="cnt">{len(a)}</span></a>'
                 for n, a in people_sorted)

index_body = f"""<a class="skip-link" href="#main">本文へ移動</a>
<div class="topline"></div>
{header_nav("home")}


<main class="main" id="main"><div class="container"><div class="main-grid">
  <div class="col-left">
    <section class="panel" id="articles-panel">
      <div class="panel-head" id="articles"><h2 class="panel-title">議題まとめ</h2><span class="panel-count">{len(ARTICLES)}本</span></div>
      <div class="articles-body">{acards}</div>
    </section>
  </div>
  <aside class="side-col">
    <section class="about">
      <h3>このサイトについて</h3>
      <p>本サイトは、<a href="{GIJI}/" target="_blank" rel="noopener">小金井市議会 非公式会議録</a>（作成・運営：小金井市議会議員 ながとり太郎）を原典として、
      AIが<strong>検索・議員・議題まとめ</strong>の切り口で再編集した非公式のアーカイブです（読み取り専用。閲覧者が編集する仕組みは持ちません）。</p>
      <ul>
        <li>要約・記事・抽出はAIによる自動生成のため、誤りを含む可能性があります。</li>
        <li>正確な発言内容は、原典（全文・動画頭出しつき）、市議会の公式会議録またはYouTube動画をご確認ください。</li>
        <li>本サイトの内容に基づく判断・行動について、作成者は一切の責任を負いません。</li>
      </ul>
      <div class="srcs">原典：<a href="{GIJI}/" target="_blank" rel="noopener">小金井市議会 非公式会議録</a><br>
      動画原本：<a href="{YT_CH}" target="_blank" rel="noopener">小金井市議会 YouTubeチャンネル</a><br>
      公式：<a href="{KENSAKU}" target="_blank" rel="noopener">小金井市議会 会議録検索システム</a></div>
    </section>
    <section class="panel">
      <div class="panel-head"><h2 class="panel-title">クイックリンク</h2></div>
      <div class="quick-body">
        <a class="qbtn" href="list.html">📋 会議一覧（会期別）</a>
        <a class="qbtn" href="{GIJI}/" target="_blank" rel="noopener">📖 原典アーカイブ<span class="external">↗</span></a>
        <a class="qbtn" href="{YT_CH}" target="_blank" rel="noopener">🎬 市議会YouTube<span class="external">↗</span></a>
        <a class="qbtn" href="{KENSAKU}" target="_blank" rel="noopener">🏛 公式会議録検索<span class="external">↗</span></a>
      </div>
    </section>
    
    <section class="panel">
      <div class="panel-head"><h2 class="panel-title">議員から探す</h2><span class="panel-count">{len(people)}人</span></div>
      <div class="people-body">{pchips}</div>
    </section>
  </aside>
</div></div></main>
{site_footer(0)}
"""
open(os.path.join(OUT, "index.html"), "w", encoding="utf-8").write(
    shell("小金井市議会 会議録アーカイブ（非公式）", index_body))

# =========================================================
# 会議一覧ページ
# =========================================================
facet_chips = (f'<button class="chip facet is-active" data-cat="all" style="border-color:var(--primary-line);">'
               f'<span class="cdot" style="background:{DOT["all"]};"></span>すべて（{len(docs)}）</button>')
for c in CATS:
    facet_chips += (f'<button class="chip facet" data-cat="{esc(c)}">'
                    f'<span class="cdot" style="background:{DOT[c]};"></span>{esc(c)}（{catcount[c]}）</button>')

session_panels = ""
for name, files in sessions:
    rows = ""
    for f in files:
        if f not in docs: continue
        d = docs[f]
        rows += f"""<tr data-cat="{esc(d["cat"])}">
  <td class="td-date"><span class="date">{esc(d["slash"])}</span></td>
  <td class="td-kind">{kind(d["cat"])}</td>
  <td class="td-title"><a class="meeting-link" href="m/{d["file"]}">{esc(d["type"])}</a></td>
  <td class="td-status">{status_badge(d)}</td>
  <td class="td-action"><a class="action-link" href="m/{d["file"]}" aria-label="開く">›</a></td>
</tr>"""
    session_panels += f"""<section class="panel session-panel" style="margin-bottom:22px;">
  <div class="panel-head"><h2 class="panel-title">{esc(name)}</h2><span class="panel-count">{len(files)}件</span></div>
  <div class="table-scroll"><table class="meeting-table">
    <colgroup><col class="col-date"><col class="col-kind"><col><col class="col-status"><col class="col-action"></colgroup>
    <thead><tr><th>開催日</th><th>会議種別</th><th>会議名</th><th>ステータス</th><th><span class="visually-hidden">詳細</span></th></tr></thead>
    <tbody>{rows}</tbody>
  </table></div>
</section>"""

list_body = f"""<div class="topline"></div>
{header_nav("list")}
<main class="main" id="main"><div class="container">
  {BANNER}
  <div class="popular" style="margin:14px 0 20px;"><span class="label">絞り込み：</span>{facet_chips}</div>
  {session_panels}
</div></main>
{site_footer(0)}
<script>
(function(){{
  var cat='all';
  document.querySelectorAll('.facet').forEach(function(b){{
    b.addEventListener('click',function(){{
      document.querySelectorAll('.facet').forEach(function(x){{x.classList.remove('is-active');x.style.borderColor='';}});
      b.classList.add('is-active');b.style.borderColor='var(--primary-line)';
      cat=b.getAttribute('data-cat');
      document.querySelectorAll('tr[data-cat]').forEach(function(r){{
        r.classList.toggle('hidden',!(cat==='all'||r.getAttribute('data-cat')===cat));
      }});
      document.querySelectorAll('.session-panel').forEach(function(p){{
        p.classList.toggle('hidden',!p.querySelector('tr[data-cat]:not(.hidden)'));
      }});
    }});
  }});
}})();
</script>
"""
open(os.path.join(OUT, "list.html"), "w", encoding="utf-8").write(
    shell("会議一覧｜小金井市議会 会議録アーカイブ（非公式）", list_body))

print("WROTE:", OUT, "| meetings:", len(docs), "| people:", len(people), "| articles:", len(ARTICLES))
