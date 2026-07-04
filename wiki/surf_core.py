#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
surf_core — 「議論の海サーフ」連想ナビの単一ロジック源。

ここが POLICY §9 の生命線：エッジ（＝連想リンク）は **原典に根拠のある機械的共起のみ**。
AIの意味推論・編集者の主観でリンクを張らない。チップ・雲の大小も機械カウントのみ。

このモジュールは I/O を持たない純ロジック。入力（構造化済みの会議・記事・会期）を受け取り、
surf/ 配下に配置する {相対パス: 中身} の dict と統計を返す。
呼び出し側：
  - wiki/build_surf.py … コミット済み検証データ（search.json/articles.py/list.html）から wiki/surf/ を生成
  - wiki/generate.py  … 本番パイプライン内で OUT/surf/ を生成（原典 src/ から。より完全な bills を渡す）
両者が同じ本モジュールを使うことで「どのエッジを張るか」は必ず一致する。

入力の型：
  meetings: [ {"f":ファイル名, "t":会議名, "c":会議種別, "w":和暦日付, "members":[議員名...], "bills":[生の議案文字列...]} ]
  articles: [ {"slug","title","cat","wareki","people":[議員名...], "src":[会議ファイル名...], "tags":[...]} ]
  sessions: [ (会期名, [会議ファイル名...]) ]
"""
import re, html, json

def esc(s): return html.escape(str(s))

# ---- カテゴリ色（本体 generate.py の DOT と同一トーン） ----
DOT = {"本会議":"#c2410c","予算特別委員会":"#b45309","常任委員会":"#1d4ed8",
       "議会運営委員会":"#7c3aed","特別委員会・協議会":"#0f766e","その他":"#767676"}
def dot(cat): return DOT.get(cat, "#767676")
CATS = ["本会議","常任委員会","予算特別委員会","議会運営委員会","特別委員会・協議会"]

# ---- 議案・陳情番号の抽出（verify.py V3 と同一の正規表現） ----
BILL_RE = re.compile(r"(議案|意見書案|陳情|請願)第(\d+)号")
PFX = {"議案":"gian","意見書案":"ikensho","陳情":"chinjo","請願":"seigan"}
def bill_tokens(s):
    """文字列から (表示名, slug) を全部返す。同一 slug は呼び出し側で dedup。"""
    out = []
    for m in BILL_RE.finditer(str(s)):
        out.append((f"{m.group(1)}第{m.group(2)}号", f"{PFX[m.group(1)]}-{m.group(2)}"))
    return out

# ---- ワードクラウドのサイズ写像（唯一の決定的な式・監査可能） ----
# 面積 ≒ 出現回数。cnt/cmax の平方根を rem に線形写像。ここを変える時は POLICY にも明記する。
CLOUD_MIN, CLOUD_SPAN, CLOUD_GAMMA = 0.82, 1.5, 0.5
def cloud_size(cnt, cmax):
    return CLOUD_MIN + CLOUD_SPAN * (cnt / (cmax or 1)) ** CLOUD_GAMMA


def build(meetings, articles, sessions, note="", caveat=""):
    # ---------- slug 割当（決定的：ファイル名/氏名でソート） ----------
    meetings = list(meetings)
    mslug = {mt["f"]: f"m{i:02d}" for i, mt in enumerate(sorted(meetings, key=lambda x: x["f"]))}
    mby = {mt["f"]: mt for mt in meetings}
    people = sorted({p for mt in meetings for p in mt["members"]})
    pslug = {n: f"p{i:02d}" for i, n in enumerate(people)}
    cslug = {c: f"c{i}" for i, c in enumerate(CATS)}
    sslug = {name: f"s{i}" for i, (name, _) in enumerate(sessions)}

    # ---------- インデックス（すべて機械的共起） ----------
    person_meetings = {n: [] for n in people}
    for mt in meetings:
        for p in mt["members"]:
            person_meetings[p].append(mt["f"])
    # 議員⇄議員（同一会議への共登壇。重み＝共に出た会議数）
    person_co = {n: {} for n in people}
    for mt in meetings:
        ppl = mt["members"]
        for i in range(len(ppl)):
            for j in range(len(ppl)):
                if i != j:
                    person_co[ppl[i]][ppl[j]] = person_co[ppl[i]].get(ppl[j], 0) + 1
    # 議案・陳情番号 → 会議
    bill_disp, bill_meetings = {}, {}
    meeting_bills = {mt["f"]: [] for mt in meetings}
    for mt in meetings:
        seen = set()
        for raw in mt["bills"]:
            for disp, slug in bill_tokens(raw):
                bill_disp[slug] = disp
                if slug not in seen:
                    seen.add(slug)
                    bill_meetings.setdefault(slug, []).append(mt["f"])
        meeting_bills[mt["f"]] = sorted(seen)
    # 会期 → 会議 / 会議 → 会期
    session_meetings = {name: [f for f in files if f in mby] for name, files in sessions}
    meeting_session = {}
    for name, files in sessions:
        for f in files:
            if f in mby:
                meeting_session[f] = name
    # カテゴリ → 会議
    cat_meetings = {c: [mt["f"] for mt in meetings if mt["c"] == c] for c in CATS}
    # 記事 → 議員 / 会議 / 議案
    art_by_slug = {a["slug"]: a for a in articles}
    person_articles = {n: [] for n in people}
    for a in articles:
        for p in a.get("people", []):
            if p in person_articles:
                person_articles[p].append(a["slug"])
    meeting_articles = {mt["f"]: [] for mt in meetings}
    for a in articles:
        for f in a.get("src", []):
            if f in meeting_articles:
                meeting_articles[f].append(a["slug"])
    bill_articles, article_bills = {}, {}
    for a in articles:
        bs = []
        for disp, slug in bill_tokens(a["title"]):
            bs.append(slug)
            bill_disp.setdefault(slug, disp)
            bill_articles.setdefault(slug, []).append(a["slug"])
        article_bills[a["slug"]] = sorted(set(bs))

    # ---------- 共通レンダリング ----------
    def shell(title, body, depth):
        rel = "../" * depth
        proto = f'<span class="proto">{esc(note)}</span>' if note else ""
        return (f'<!DOCTYPE html><html lang="ja"><head><meta charset="UTF-8">'
                f'<meta name="viewport" content="width=device-width, initial-scale=1">'
                f'<title>{esc(title)}｜議論の海サーフ</title>'
                f'<link rel="stylesheet" href="{rel}surf.css"></head><body>'
                f'<header class="shd"><a class="brand" href="{rel}index.html">'
                f'<span class="mk">会</span>議論の海サーフ{proto}</a>'
                f'<span class="disc">連想＝関係の証明ではありません。'
                f'リンクは「原典に共に現れた」ことだけを示します。</span></header>'
                f'<main class="wrap">{body}</main></body></html>')

    def chip(href, label, cat=None):
        d = f'<span class="cd" style="background:{dot(cat)}"></span>' if cat else ""
        return f'<a class="chip" href="{href}">{d}{esc(label)}</a>'

    def chips_block(title, note_, items):
        if not items: return ""
        return (f'<section class="grp"><h2>{esc(title)}<span class="rel">{esc(note_)}</span></h2>'
                f'<div class="chips">{"".join(items)}</div></section>')

    def hop(neighbors):
        """静的セレンディピティ：ビルド時に決定的に隣を1つ選ぶ（先頭）。JS不要。"""
        if not neighbors: return ""
        href, label = neighbors[0]
        return f'<a class="hop" href="{href}">🎲 となりへ飛ぶ → {esc(label)}</a>'

    GIJI = "https://toritarosan.github.io/Gijiroku1"
    pages = {}

    # ---- 会議ハブ ----
    def render_meeting(mt):
        f = mt["f"]; d = 1; rs = "../"; site = "../../"
        mem = [chip(f'{rs}p/{pslug[p]}.html', p) for p in mt["members"] if p in pslug]
        bil = [chip(f'{rs}b/{s}.html', bill_disp[s]) for s in meeting_bills[f]]
        art = [chip(f'{rs}a/{s}.html', art_by_slug[s]["title"]) for s in meeting_articles[f] if s in art_by_slug]
        catc = [chip(f'{rs}c/{cslug[mt["c"]]}.html', mt["c"], mt["c"])] if mt["c"] in cslug else []
        sess = ([chip(f'{rs}s/{sslug[meeting_session[f]]}.html', meeting_session[f])]
                if f in meeting_session else [])
        nb = ([(f'{rs}p/{pslug[mt["members"][0]]}.html', mt["members"][0])] if mt["members"] else
              [(f'{rs}b/{meeting_bills[f][0]}.html', bill_disp[meeting_bills[f][0]])] if meeting_bills[f] else
              ([(f'{rs}c/{cslug[mt["c"]]}.html', mt["c"])] if mt["c"] in cslug else []))
        body = (f'<div class="crumb"><span class="cd" style="background:{dot(mt["c"])}"></span>会議 · {esc(mt["w"])}</div>'
                f'<h1>{esc(mt["t"])}</h1>{hop(nb)}'
                + (chips_block("登壇した議員", "この会議に登壇", mem)
                   or '<p class="empty">この会議に登壇議員データはありません（手続き中心の会議）。会期・種別で他会議へ繋がります。</p>')
                + chips_block("扱った議案・陳情", "この会議で審議", bil)
                + chips_block("この会議を出典とする議題まとめ", "出典＝この会議", art)
                + chips_block("会期", "同じ会期の会議へ", sess)
                + chips_block("会議種別", "同じ種別の会議へ", catc)
                + f'<p class="src">本番の会議ページ：<a href="{site}m/{esc(f)}">{esc(mt["t"])}（本サイト）</a> ／ '
                  f'<a href="{GIJI}/{esc(f)}" target="_blank" rel="noopener">原典 ↗</a></p>')
        pages[f'm/{mslug[f]}.html'] = shell(mt["t"], body, d)

    # ---- 議員ハブ ----
    def render_person(n):
        rs = "../"
        mts = person_meetings[n]
        mchips = [chip(f'{rs}m/{mslug[f]}.html', mby[f]["t"], mby[f]["c"]) for f in mts]
        co = sorted(person_co[n].items(), key=lambda x: -x[1])
        cochips = [chip(f'{rs}p/{pslug[c]}.html', f'{c}（{cnt}）') for c, cnt in co if c in pslug]
        arts = [chip(f'{rs}a/{s}.html', art_by_slug[s]["title"]) for s in person_articles[n] if s in art_by_slug]
        nb = [(f'{rs}m/{mslug[mts[0]]}.html', mby[mts[0]]["t"])] if mts else []
        body = (f'<div class="crumb"><span class="cd" style="background:#20242a"></span>議員</div>'
                f'<h1>{esc(n)} <span class="sub">議員</span></h1>{hop(nb)}'
                + chips_block(f"登壇した会議（{len(mchips)}）", "この議員が登壇", mchips)
                + chips_block("同じ会議に登壇した議員", "共登壇（数字＝共に出た会議数）", cochips)
                + chips_block("登場する議題まとめ", "この議員が登場", arts)
                + '<p class="note2">※ 登壇記録は会議録の見出しから機械抽出。'
                  '人名は verify.py の原典照合（V3）を通っています。</p>')
        pages[f'p/{pslug[n]}.html'] = shell(f"{n} 議員", body, 1)

    # ---- 議案・陳情ハブ ----
    def render_bill(slug):
        rs = "../"
        mts = bill_meetings.get(slug, [])
        mchips = [chip(f'{rs}m/{mslug[f]}.html', mby[f]["t"], mby[f]["c"]) for f in mts if f in mslug]
        arts = [chip(f'{rs}a/{s}.html', art_by_slug[s]["title"]) for s in bill_articles.get(slug, []) if s in art_by_slug]
        nb = [(f'{rs}m/{mslug[mts[0]]}.html', mby[mts[0]]["t"])] if mts else []
        body = (f'<div class="crumb"><span class="cd" style="background:#8a5a00"></span>議案・陳情</div>'
                f'<h1>{esc(bill_disp[slug])}</h1>{hop(nb)}'
                + chips_block("この番号を扱う会議", "同じ議案・陳情番号を審議", mchips)
                + chips_block("この番号に触れる議題まとめ", "タイトルに同番号", arts)
                + '<p class="note2">※ 番号は verify.py V3 と同一の正規表現で抽出。'
                  '同じ番号を扱う会議どうしを機械的に接続しています。</p>')
        pages[f'b/{slug}.html'] = shell(bill_disp[slug], body, 1)

    # ---- 会議種別ハブ ----
    def render_cat(c):
        rs = "../"
        mchips = [chip(f'{rs}m/{mslug[f]}.html', mby[f]["t"]) for f in cat_meetings[c] if f in mslug]
        body = (f'<div class="crumb"><span class="cd" style="background:{dot(c)}"></span>会議種別</div>'
                f'<h1>{esc(c)}</h1>'
                + chips_block(f"この種別の会議（{len(mchips)}）", "同じ会議種別", mchips))
        pages[f'c/{cslug[c]}.html'] = shell(c, body, 1)

    # ---- 会期ハブ ----
    def render_session(name):
        rs = "../"
        mchips = [chip(f'{rs}m/{mslug[f]}.html', mby[f]["t"], mby[f]["c"]) for f in session_meetings[name] if f in mslug]
        body = (f'<div class="crumb"><span class="cd" style="background:#0f766e"></span>会期</div>'
                f'<h1>{esc(name)}</h1>'
                + chips_block(f"この会期の会議（{len(mchips)}）", "同じ会期に開催", mchips))
        pages[f's/{sslug[name]}.html'] = shell(name, body, 1)

    # ---- 記事ハブ ----
    def render_article(a):
        rs = "../"; site = "../../"
        pchips = [chip(f'{rs}p/{pslug[p]}.html', p) for p in a.get("people", []) if p in pslug]
        src = [chip(f'{rs}m/{mslug[f]}.html', mby[f]["t"], mby[f]["c"]) for f in a.get("src", []) if f in mslug]
        bch = [chip(f'{rs}b/{s}.html', bill_disp[s]) for s in article_bills.get(a["slug"], [])]
        tagchips = "".join(f'<span class="tag-x">#{esc(t)}</span>' for t in a.get("tags", [])) or '<span class="empty2">—</span>'
        nb = ([(f'{rs}p/{pslug[a["people"][0]]}.html', a["people"][0])] if a.get("people") else
              [(f'{rs}m/{mslug[a["src"][0]]}.html', mby[a["src"][0]]["t"])] if (a.get("src") and a["src"][0] in mby) else [])
        body = (f'<div class="crumb"><span class="cd" style="background:{dot(a["cat"])}"></span>議題まとめ · {esc(a.get("wareki",""))}</div>'
                f'<h1>{esc(a["title"])}</h1>{hop(nb)}'
                + chips_block("登場する議員", "この記事に登場（V3で原典照合）", pchips)
                + chips_block("出典となった会議", "この記事の出典", src)
                + chips_block("関係する議案・陳情", "タイトルの番号", bch)
                + '<section class="grp"><h2>タグ<span class="rel">編集ラベル・未検証（リンクなし）</span></h2>'
                  f'<div class="chips">{tagchips}</div></section>'
                + f'<p class="src">本番の記事：<a href="{site}a/{esc(a["slug"])}.html">{esc(a["title"])}（本サイト）</a></p>')
        pages[f'a/{a["slug"]}.html'] = shell(a["title"], body, 1)

    # ---- index：機械カウント・ワードクラウド ----
    def cloud(items, href_of, cat_of=None):
        if not items: return ""
        cmax = max(c for _, c, _ in items) or 1
        out = []
        for label, cnt, key in sorted(items, key=lambda x: -x[1]):
            sz = cloud_size(cnt, cmax)
            col = dot(cat_of(key)) if cat_of else "#20242a"
            out.append(f'<a class="w" style="font-size:{sz:.2f}rem;color:{col}" '
                       f'href="{href_of(key)}">{esc(label)}<span class="wc">{cnt}</span></a>')
        return '<div class="cloud">' + "".join(out) + "</div>"

    ppl_items = [(n, len(person_meetings[n]), n) for n in people if person_meetings[n]]
    bill_items = [(bill_disp[s], len(bill_meetings.get(s, [])), s) for s in bill_meetings if bill_meetings.get(s)]
    cat_items = [(c, len(cat_meetings[c]), c) for c in CATS if cat_meetings[c]]
    sess_items = [(name, len(session_meetings[name]), name) for name, _ in sessions if session_meetings[name]]

    index_body = (
        '<div class="hero"><h1>議論の海を、リンクで漂う</h1>'
        '<p>階層で辿るのではなく、大きい語＝よく登場する議員・議案から飛び込み、'
        'チップを連打して会議→議員→同じ議案を扱う別会議…と横へ滑っていく連想ナビです。'
        '<b>語の大きさは機械的な出現回数だけ</b>で決まり、リンクは<b>原典に共に現れた事実</b>だけを表します。</p>'
        f'<p class="mini">会議{len(meetings)}・議員{len(people)}・議案/陳情{len(bill_items)}種・会期{len(sess_items)}・記事{len(articles)}。'
        'リンクの根拠と免責は各ページ下部に明記しています。'
        + (f'<br>{esc(caveat)}' if caveat else "") + '</p></div>'
        f'<section class="grp"><h2>議員<span class="rel">大きいほど登壇会議が多い</span></h2>'
        f'{cloud(ppl_items, lambda k: f"p/{pslug[k]}.html")}</section>'
        f'<section class="grp"><h2>議案・陳情<span class="rel">大きいほど扱う会議が多い</span></h2>'
        f'{cloud(bill_items, lambda k: f"b/{k}.html")}</section>'
        f'<section class="grp"><h2>会議種別<span class="rel">大きいほど会議数が多い</span></h2>'
        f'{cloud(cat_items, lambda k: f"c/{cslug[k]}.html", cat_of=lambda k: k)}</section>'
        f'<section class="grp"><h2>会期<span class="rel">大きいほど会議数が多い</span></h2>'
        f'{cloud(sess_items, lambda k: f"s/{sslug[k]}.html")}</section>'
    )
    pages["index.html"] = shell("議論の海サーフ", index_body, 0)

    # ---- 各ページ生成 ----
    for mt in meetings: render_meeting(mt)
    for n in people: render_person(n)
    for slug in bill_meetings:
        if bill_meetings[slug]: render_bill(slug)
    for c in CATS:
        if cat_meetings[c]: render_cat(c)
    for name, _ in sessions:
        if session_meetings[name]: render_session(name)
    for a in articles: render_article(a)

    # ---- graph.json（監査用。tags は端点にしない＝rel!='tag' を保証） ----
    nodes, edges = [], []
    for mt in meetings: nodes.append({"id": mslug[mt["f"]], "kind": "meeting", "label": mt["t"]})
    for n in people: nodes.append({"id": pslug[n], "kind": "person", "label": n})
    for slug in bill_meetings:
        if bill_meetings[slug]: nodes.append({"id": slug, "kind": "bill", "label": bill_disp[slug]})
    for c in CATS:
        if cat_meetings[c]: nodes.append({"id": cslug[c], "kind": "category", "label": c})
    for name, _ in sessions:
        if session_meetings[name]: nodes.append({"id": sslug[name], "kind": "session", "label": name})
    for a in articles: nodes.append({"id": a["slug"], "kind": "article", "label": a["title"]})

    for mt in meetings:
        f = mt["f"]
        for p in mt["members"]:
            if p in pslug: edges.append({"a": mslug[f], "b": pslug[p], "rel": "member"})
        for s in meeting_bills[f]:
            edges.append({"a": mslug[f], "b": s, "rel": "bill"})
        if mt["c"] in cslug: edges.append({"a": mslug[f], "b": cslug[mt["c"]], "rel": "category"})
        if f in meeting_session: edges.append({"a": mslug[f], "b": sslug[meeting_session[f]], "rel": "session"})
    seen_co = set()
    for n in people:
        for c, w in person_co[n].items():
            key = tuple(sorted((pslug[n], pslug[c])))
            if key not in seen_co:
                seen_co.add(key)
                edges.append({"a": key[0], "b": key[1], "rel": "co-appear", "w": w})
    for a in articles:
        for p in a.get("people", []):
            if p in pslug: edges.append({"a": a["slug"], "b": pslug[p], "rel": "article-person"})
        for f in a.get("src", []):
            if f in mslug: edges.append({"a": a["slug"], "b": mslug[f], "rel": "article-src"})
        for s in article_bills.get(a["slug"], []):
            edges.append({"a": a["slug"], "b": s, "rel": "article-bill"})

    assert all(e["rel"] != "tag" for e in edges), "graph.json に tag エッジが混入（§9違反）"
    pages["graph.json"] = json.dumps(
        {"note": "エッジは原典に根拠のある機械的共起のみ。tagは端点にしない。",
         "nodes": nodes, "edges": edges}, ensure_ascii=False)

    stats = {"meetings": len(meetings), "people": len(people),
             "bills": sum(1 for s in bill_meetings if bill_meetings[s]),
             "cats": sum(1 for c in CATS if cat_meetings[c]),
             "sessions": len(sess_items), "articles": len(articles),
             "nodes": len(nodes), "edges": len(edges)}
    # slug マップは呼び出し側（generate.py）が本体ページ→サーフハブの導線リンクを張るのに使う
    maps = {"mslug": mslug, "pslug": pslug, "cslug": cslug, "sslug": sslug}
    return pages, stats, maps


# ---- surf.css（自己完結・全ページ共通。両アダプタで同一） ----
CSS = """/* 議論の海サーフ — 連想ナビ（JSゼロ） */
:root{--bg:#eceae6;--surface:#fff;--ink:#20242a;--text:#3a3f45;--muted:#6b7075;
  --border:#e2ddd4;--amber:#e8b04b;--line:#e6e3dd;}
*{box-sizing:border-box;}
body{margin:0;background:var(--bg);color:var(--text);
  font-family:-apple-system,BlinkMacSystemFont,"Hiragino Sans","Noto Sans JP",sans-serif;line-height:1.8;}
a{text-decoration:none;color:inherit;}
.shd{position:sticky;top:0;z-index:20;background:var(--surface);border-bottom:1px solid var(--border);
  display:flex;align-items:center;gap:14px;flex-wrap:wrap;padding:10px 20px;}
.brand{display:flex;align-items:center;gap:9px;font-weight:900;color:var(--ink);font-size:1rem;}
.mk{width:28px;height:28px;background:var(--amber);color:#20242a;font-weight:900;display:grid;place-items:center;border-radius:4px;font-size:.86rem;}
.proto{font-size:.62rem;font-weight:800;letter-spacing:.04em;color:#8a5a00;background:#fdf6e6;border:1px solid #ecdcae;border-radius:999px;padding:2px 8px;margin-left:2px;}
.disc{font-size:.72rem;color:var(--muted);}
.wrap{max-width:960px;margin:0 auto;padding:24px 20px 70px;}
.crumb{display:flex;align-items:center;gap:8px;font-size:.78rem;color:var(--muted);margin-bottom:8px;}
.cd{width:9px;height:9px;border-radius:2px;display:inline-block;flex:none;}
h1{font-size:clamp(1.4rem,3vw,2rem);font-weight:900;color:var(--ink);line-height:1.3;margin:0 0 6px;}
h1 .sub{font-size:.6em;font-weight:700;color:var(--muted);}
.hop{display:inline-block;margin:8px 0 4px;font-size:.8rem;font-weight:700;color:#8a5a00;
  background:#fdf6e6;border:1px solid #ecdcae;border-radius:999px;padding:6px 13px;}
.hop:hover{background:#f9edd2;}
.grp{margin:24px 0 0;}
.grp h2{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;font-size:1rem;font-weight:900;color:var(--ink);
  margin:0 0 10px;padding-bottom:6px;border-bottom:1px solid var(--border);}
.grp h2 .rel{font-size:.72rem;font-weight:600;color:var(--muted);}
.chips{display:flex;flex-wrap:wrap;gap:8px;}
.chip{display:inline-flex;align-items:center;gap:7px;background:var(--surface);border:1px solid var(--border);
  border-radius:999px;padding:7px 13px;font-size:.85rem;font-weight:600;color:var(--ink);
  transition:transform .1s,box-shadow .1s,border-color .1s;}
.chip:hover{transform:translateY(-1px);box-shadow:0 4px 10px rgba(0,0,0,.08);border-color:#c9c2b4;}
.empty,.empty2{color:var(--muted);font-size:.85rem;}
.note2{margin-top:18px;font-size:.76rem;color:var(--muted);border-top:1px dashed var(--border);padding-top:10px;}
.src{margin-top:16px;font-size:.8rem;color:var(--muted);}
.src a{color:#1d4ed8;font-weight:600;}.src a:hover{text-decoration:underline;}
.tag-x{display:inline-flex;align-items:center;background:#f2f0ec;border:1px dashed #cfc9bc;color:#8a857a;
  border-radius:999px;padding:6px 12px;font-size:.82rem;}
.hero{background:var(--surface);border:1px solid var(--border);border-left:4px solid var(--amber);
  border-radius:8px;padding:20px 22px;margin-bottom:8px;}
.hero h1{margin:0 0 8px;}
.hero p{margin:0 0 8px;font-size:.92rem;color:var(--text);}
.hero b{color:var(--ink);}
.hero .mini{font-size:.76rem;color:var(--muted);}
.cloud{display:flex;flex-wrap:wrap;gap:4px 14px;align-items:baseline;padding:4px 0;}
.w{font-weight:800;line-height:1.5;transition:opacity .1s;}
.w:hover{text-decoration:underline;text-underline-offset:3px;}
.wc{font-size:.6em;font-weight:600;color:#9a9ea3;vertical-align:super;margin-left:1px;}
@media(max-width:600px){.disc{display:none;}}
"""
