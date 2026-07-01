#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify.py — 議題まとめ記事の機械検証（原典突合）

目的：AIが生成した記事に、原典に存在しない情報（ハルシネーション）や
評価的・解釈的な表現が混入していないかを機械的に検証する。
1件でも ERROR があれば generate.py は記事の出力を中止する。

検証項目:
  V1 数値照合   : 記事中のすべての数値が単位込み・原典の表記どおりに存在すること（表記ゆれは正規化で吸収）
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
    for tok in extract_numbers(normalize(full_plain)):
        if found_with_boundary(tok, norm_sources):
            continue
        if any(tok == w or tok in w for w in wl):
            continue
        errors.append(f"V1 原典に存在しない数値: '{tok}'")

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
    for w in FORBIDDEN:
        if w in full_plain:
            errors.append(f"V4 禁止語（評価的・扇情的表現）: '{w}'")

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
