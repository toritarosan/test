#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify.py — 議題まとめ記事の機械検証（原典突合）

目的：AIが生成した記事に、原典に存在しない情報（ハルシネーション）や
評価的・解釈的な表現が混入していないかを機械的に検証する。
1件でも ERROR があれば generate.py は記事の出力を中止する。

検証項目:
  V1 数値照合   : 記事中のすべての数値が単位込み・原典の表記どおりに存在すること（表記ゆれは正規化で吸収）
  V1b 日付照合   : 記事中の日付（年月日・月日）が複合文字列として原典に存在すること（捏造日付の検出）
  V2 引用照合   : 記事中の「」内の語句が原典本文に逐語で存在すること
  V3 固有名詞照合: 議員名・議案番号等が原典本文に存在すること
  V4 禁止語     : 評価的・扇情的な語（追及・糾弾・迫る等）を含まないこと
  V5 帰属チェック : 主張・評価を含む文（批判/懸念/べき等）は、発話者への
                   帰属動詞（述べた・質問した・答弁した等）を伴うこと
"""
import re, html, os

# ---------------- 正規化 ----------------
_Z2H = str.maketrans("０１２３４５６７８９，．：（）", "0123456789,.:()")
def normalize(s):
    s = html.unescape(s)
    s = s.translate(_Z2H)
    s = s.replace(",", "").replace("，", "")
    s = s.replace("ヶ", "か").replace("ヵ", "か").replace("箇", "か").replace("カ", "か")
    s = s.replace("〜", "~").replace("～", "~")
    s = s.replace("㎡", "平米").replace("平方メートル", "平米")
    s = s.replace("％", "%").replace("パーセント", "%")
    s = re.sub(r"\s+", "", s)
    return s

def strip_tags(s):
    return html.unescape(re.sub(r"<[^>]+>", " ", s))

# ---------------- 語彙規則 ----------------
# 禁止語（記事のどこにあっても ERROR）：評価・扇情・追及型の表現
FORBIDDEN = [
    "追及", "糾弾", "断罪", "迫った", "迫る", "攻防", "波紋", "衝撃", "露呈",
    "杜撰", "ずさん", "スクープ", "驚き", "疑惑", "紛糾", "炎上", "泥沼",
    "——", "!?", "！？", "必見", "注目の", "話題の", "衝突",
]
# 帰属必須語（含む文に帰属動詞がなければ ERROR）：
# 立場・評価を示す語は、誰の発言かを明示して報告する形でのみ使用できる
ATTRIB_REQUIRED = ["批判", "懸念", "べき", "疑問", "問題視", "評価", "主張", "反対", "賛成", "指摘"]
ATTRIB_VERBS = ["述べた", "質問", "答弁", "説明", "指摘した", "要望", "求めた", "確認", "示した",
                "主張した", "提案", "意見", "立場", "討論", "とした", "挙げた", "提示", "記録する"]

# ---------------- 数値抽出 ----------------
# 複合数値（例: 549億614万9000円 / 3兆1千億円）を1トークンとして抽出する
UNIT = r"(?:円|人|件|本|平米|㎡|%|％|年度|年|か月|月|日|回|号|区|市|会派|議席|周年|時間|分|秒|世帯|事業所|路線|園|校|台|名)?"
NUM_TOKEN = re.compile(r"(?:\d+(?:\.\d+)?(?:兆|億|万|千|百)?)+" + UNIT)

def extract_numbers(text):
    return [m.group(0) for m in NUM_TOKEN.finditer(text)]

def found_with_boundary(tok, source):
    """数値トークンが原典に「数値の途中でない位置」から現れるか
    （例: '5億' が '238.5億' の一部に一致するのを防ぐ）"""
    return re.search(r"(?<![0-9.兆億万千百])" + re.escape(tok), source) is not None

def sentences(text):
    return re.split(r"[。\n]", text)

# ---------------- 検証本体 ----------------
def verify_article(article, source_texts, date_whitelist=()):
    """
    article: dict（articles.py の1要素）
    source_texts: 出典原典（src=）の本文プレーンテキストのリスト
    date_whitelist: ファイル名等のメタデータ由来で正当化される数値トークン集合
    return: (errors, warnings)  それぞれ文字列リスト
    """
    errors, warnings = [], []
    body_plain = strip_tags(article["body"])
    full_plain = article["title"] + "\n" + article["lead"] + "\n" + body_plain
    norm_sources = normalize("\n".join(source_texts))
    norm_full = normalize(full_plain)

    wl = set()
    for w in date_whitelist:
        wl.add(normalize(w))

    # V1 数値照合（複合数値を一体で、数字境界つきで照合）
    # 549億614万9000円 のような具体的な複合数値・金額・件数は、その数値トークンが
    # 原典に「数値の途中でない位置」から現れることを要求する（不在なら ERROR）。
    norm_full_v1 = normalize(full_plain)
    for m in NUM_TOKEN.finditer(norm_full_v1):
        tok = m.group(0)
        if any(tok == w or tok in w for w in wl):
            continue
        if not found_with_boundary(tok, norm_sources):
            errors.append(f"V1 原典に存在しない数値: '{tok}'")

    # V1b 日付の複合照合（捏造日付の検出）
    # 「5月」「26日」は単独では原典の別箇所に高頻度で存在するため、
    # トークン単位照合では「令和8年5月26日」のような捏造日付をすり抜ける。
    # そこで日付は複合文字列（年月日／月日）として一体で原典に存在することを要求する。
    # 長いパターン優先の単一正規表現で「令和N年M月D日」を一体マッチさせ、
    # 同じ箇所から「M月D日」等が二重にマッチするのを防ぐ（非重複の finditer）。
    DATE_RE = re.compile(r"令和\d+年\d+月\d+日|\d+年\d+月\d+日|\d+月\d+日")
    seen_dates = set()
    for m in DATE_RE.finditer(norm_full_v1):
        md = m.group(0)
        if md in seen_dates:
            continue
        seen_dates.add(md)
        if md in wl or ("令和" + md) in wl:
            continue
        # 原典側は「4月の14日」のように年・月の後に「の」を挟む場合がある。
        # 日付照合はこの「の」の有無を許容し、令和接頭辞の有無も吸収する。
        flex = md.replace("年", "年の?").replace("月", "月の?")
        if re.search(flex, norm_sources) or re.search("令和" + flex, norm_sources):
            continue
        errors.append(f"V1b 原典に存在しない日付（捏造の疑い）: '{md}'")

    # V2 引用照合（「」内 5文字以上を対象。短い一般語は除外）
    for q in re.findall(r"「([^」]{4,40})」", full_plain):
        if normalize(q) not in norm_sources:
            errors.append(f"V2 原典に存在しない引用・鍵括弧語句: 「{q}」")

    # V3 固有名詞照合（people・議案/意見書番号）
    for name in article.get("people", []):
        if normalize(name) not in norm_sources:
            errors.append(f"V3 原典に存在しない人名: '{name}'")
    for g in re.findall(r"(議案第\d+号|意見書案第\d+号|陳情第\d+号|請願第\d+号)", full_plain):
        if normalize(g) not in norm_sources:
            errors.append(f"V3 原典に存在しない議案番号: '{g}'")

    # V4 禁止語
    # 例外: 禁止語が原典由来の固有名詞・引用の一部である場合
    # （例: 議案名「〜疑惑を全容解明することを求める意見書」）は、
    # その語の前後文脈ごと原典に逐語で存在することを条件に許容する。
    norm_full_for_v4 = normalize(full_plain)
    for w in FORBIDDEN:
        for m in re.finditer(re.escape(w), norm_full_for_v4):
            ctx = norm_full_for_v4[max(0, m.start()-6):m.end()+6]
            if ctx not in norm_sources:
                errors.append(f"V4 禁止語（評価的・扇情的表現）: '{w}'（文脈: …{ctx}…）")
            break  # 同一語の重複報告は1回まで

    # V5 帰属チェック
    # 表は「質疑（議会側）／答弁（行政側）」「立場」等の列見出しで話者への帰属が
    # 構造的に明示されるため、帰属列見出しを持つ表の中は文単位チェックを免除する。
    body_html = article["body"]
    TABLE_ATTRIB_HEADERS = ("議会側", "行政側", "立場", "提案内容", "討論")
    unattributed_html = body_html
    for t in re.findall(r"<table>.*?</table>", body_html, re.S):
        if any(k in t for k in TABLE_ATTRIB_HEADERS):
            unattributed_html = unattributed_html.replace(t, " ")
    SPEAKERS = ("議員", "委員", "市長", "副市長", "議長", "行政側", "議会側",
                "教育委員会", "事務局", "会派", "市は", "市側", "提案会派")
    for sent in sentences(strip_tags(unattributed_html)):
        for w in ATTRIB_REQUIRED:
            if w in sent and not (any(v in sent for v in ATTRIB_VERBS)
                                  or any(k in sent for k in SPEAKERS)):
                errors.append(f"V5 帰属のない評価語 '{w}': …{sent.strip()[:60]}…")

    return errors, warnings


def verify_all(articles, load_source, meta_whitelist):
    """
    articles: ARTICLES リスト
    load_source: filename -> プレーンテキスト を返す関数
    meta_whitelist: filename -> 日付等トークン集合 を返す関数
    return: ok(bool), report(str)
    """
    lines, total_err = [], 0
    for a in articles:
        srcs = [load_source(f) for f in a["src"]]
        wl = set()
        for f in a["src"]:
            wl |= set(meta_whitelist(f))
        wl |= {a["date"], a["wareki"], a["date"].replace("-", "/")}
        errs, warns = verify_article(a, srcs, wl)
        status = "OK" if not errs else f"ERROR x{len(errs)}"
        lines.append(f"[{status}] {a['slug']}")
        for e in errs:
            lines.append(f"    ERROR: {e}")
        for w in warns:
            lines.append(f"    warn : {w}")
        total_err += len(errs)
    ok = total_err == 0
    lines.append(f"---- 検証結果: {'合格' if ok else '不合格'}（ERROR {total_err}件）----")
    return ok, "\n".join(lines)
