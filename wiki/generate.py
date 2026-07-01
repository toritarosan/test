#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gijiroku1（小金井市議会 非公式会議録）→ ナレッジWiki 生成スクリプト
デザイン：Gijiroku1 準拠（デジタル庁デザインシステム トークン）
入力：./src/*.html（原典62本）+ ./gijiroku_index.html
出力：OUT/（index.html, m/会議×62, p/議員×N, a/特集記事, search.json）
方針：原典の要約・構造を忠実に再利用（再要約しない）。記事は要約済み原典に基づく。
"""
import re, html, json, os, glob, sys

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

# ---------- カテゴリ配色（原典と同一） ----------
DOT = {"all":"#0017c1","本会議":"#ce0000","予算特別委員会":"#e25100","常任委員会":"#264af4",
       "議会運営委員会":"#6f23d0","特別委員会・協議会":"#1d8b56"}
PILL = {"本会議":("#a90000","#fdeeee"),"予算特別委員会":("#ac3e00","#ffeee2"),
        "常任委員会":("#0031d8","#e8f1fe"),"議会運営委員会":("#5c10be","#f1eafa"),
        "特別委員会・協議会":("#197a4b","#e6f5ec")}
def pill(cat):
    c,b = PILL.get(cat, ("#4d4d4d","#f2f2f2"))
    return f'<span class="cat" style="color:{c};background:{b};">{esc(cat)}</span>'

# ---------- 原典 index：カテゴリ & 会期マッピング ----------
idx = open("gijiroku_index.html", encoding="utf-8").read()
catmap, sessions = {}, []   # sessions: [(name, [files...])]
for m in re.finditer(r'<a[^>]*href="(R[^"]*\.html)"[^>]*>', idx):
    href, tag = m.group(1), m.group(0)
    c = re.search(r'data-cat="([^"]*)"', tag)
    catmap[href] = c.group(1) if c else "その他"
for m in re.finditer(r'<details class="session"[^>]*>(.*?)</details>', idx, re.S):
    blk = m.group(1)
    name = collapse(strip_tags(re.search(r'<span class="session-name">(.*?)</span>', blk).group(1)))
    files = re.findall(r'href="(R[^"]*\.html)"', blk)
    sessions.append((name, files))

REIWA0 = 2018
def parse_name(fn):
    m = re.match(r"R(\d+)\.(\d+)\.(\d+)_(.+)\.html$", fn)
    if not m: return None
    ry, mo, da, rest = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
    return {"file": fn, "reiwa": ry, "mo": mo, "da": da,
            "iso": f"{REIWA0+ry:04d}-{mo:02d}-{da:02d}",
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
# 特集記事（要約済み原典 R8.6.9本会議 / R8.6.17予算特別委 / R8.5.18議運 に基づく）
# =========================================================
V_HONKAIGI_69 = "bp_x5RQ6xzY"      # R8.6.9 本会議 動画1
V_YOTOKU_617 = "NDFXvQYTLek"       # R8.6.17 予算特別委員会 動画1
V_GIUN_518 = "BcRuoPzErgY"         # R8.5.18 議会運営委員会 動画1

ARTICLES = [
 dict(slug="daitai-undojo", cat="本会議", date="2026-06-09", wareki="令和8年6月9日",
  src=["R8.6.9_本会議.html", "R8.6.17_予算特別委員会.html"], video=V_HONKAIGI_69,
  people=["渡辺大三", "岸田正義"], tags=["補正予算", "学校施設", "新庁舎"],
  title="校舎改築で校庭が使えない——代替運動場の整備に3,520万円、費用対効果を問う",
  lead="小金井第一小学校の校舎改築に伴い、庁舎建設予定地の一部に代替運動場（約900平米）を整備する補正予算3,000万円が提案された。使えるのは新庁舎着工までの短期間。「3,500万円をかける価値はあるのか」——議場で費用対効果が問われた。",
  body="""
<h2 class="sec">何が提案されたか</h2>
<p>議案第57号 令和8年度一般会計補正予算（第3回）。歳入歳出にそれぞれ3,000万円を追加し、総額549億614万9,000円とする。財源は財政調整基金からの繰入金3,000万円。歳出は教育費に3,520万円を計上し（予備費520万円減額で調整）、第一小学校の校舎改築に伴う代替運動場をゴムチップ舗装・フェンス設置で庁舎建設予定地の一部に整備する。</p>
<h2 class="sec">議場での質疑</h2>
<ul>
<li><strong>渡辺大三議員</strong>：代替運動場の面積（900平米）は適切か。児童の動線確保、休日の地域開放の可能性を確認し、予算特別委員会での詳細な説明を求めた。</li>
<li><strong>岸田正義議員</strong>：利用対象者・利用時間（平日／土日）・利用期間・管理体制・面積の適切性を質した。</li>
</ul>
<h2 class="sec">市側の答弁</h2>
<p>利用者は第一小学校の児童、学童保育所、放課後子供教室。平日は主に4〜6年生の体育授業で利用し、休日はスポーツクラブ等の活用も視野に入れる。利用期間は<strong>新庁舎着工まで</strong>で、管理は学校が行い施錠する。面積は学校側の要望と現場状況を踏まえて判断したと説明した。</p>
<h2 class="sec">残された論点</h2>
<p>岸田議員は、短期間の利用に3,500万円をかける<strong>費用対効果</strong>に疑問を呈し、近隣施設利用の検討や、将来施設を閉鎖する際の児童・保護者への丁寧な説明を要望した。本議案は予算特別委員会に付託された（6月17日審査）。</p>
"""),

 dict(slug="saigai-toilet-cf", cat="予算特別委員会", date="2026-06-17", wareki="令和8年6月17日",
  src=["R8.6.17_予算特別委員会.html"], video=V_YOTOKU_617,
  people=["沖浦あつし", "太田宏徳", "水谷たかこ", "水上洋志"], tags=["防災", "クラウドファンディング", "補正予算"],
  title="災害用トイレをクラウドファンディングで——目標500万円、「オールイン方式」の勝算",
  lead="災害用トイレトレーラーの導入経費2,900万円のうち、500万円をふるさと納税型クラウドファンディングで賄う——議案第31号 補正予算（第2回）の歳入計上をめぐり、その妥当性と設計が予算特別委員会で議論された。",
  body="""
<h2 class="sec">事業の構造</h2>
<table>
<tr><th>項目</th><th>内容</th></tr>
<tr><td>導入経費</td><td>2,900万円（災害用トイレトレーラー）</td></tr>
<tr><td>東京都補助</td><td>最大1,600万円を見込む</td></tr>
<tr><td>クラウドファンディング</td><td>目標500万円（都補助との差額）</td></tr>
<tr><td>一般財源</td><td>残額 約800万円</td></tr>
</table>
<p>導入により本市の防災力向上に加え、<strong>災害派遣トイレネットワーク</strong>への参加で他自治体からの共助も期待できる（太田宏徳委員の評価）。</p>
<h2 class="sec">なぜ11月〜年末に実施するのか</h2>
<p>沖浦あつし委員の質疑に対し、ふるさと納税の駆け込み時期であること、税額控除手続きの期限、「ふるさとチョイス」「キャンプファイヤー」との連携による認知拡大を狙うためと説明。返礼品はないが、一定額以上の寄付者は氏名等を車両後部に掲載して顕彰する。車体デザインを小中学生から公募する検討も要望された。</p>
<h2 class="sec">「集まる前に歳入計上していいのか」</h2>
<p>水谷たかこ委員・水上洋志委員は、これから集まる寄付金を歳入として計上する妥当性を確認。市長は「市税収入や各種補助金と同様に見込み額として計上しており、他市の事例も参考にしている」と答弁。目標の達成如何にかかわらず寄付を受け取り事業を実施する<strong>オールイン方式</strong>で、未達でも事業は確実に推進されるとした。クラウドファンディングの実施は新型コロナ対策以来で、今回の結果を検証し、今後の運用方針を整理・検討する。</p>
"""),

 dict(slug="zaisei-645", cat="本会議", date="2026-06-09", wareki="令和8年6月9日",
  src=["R8.6.9_本会議.html"], video=V_HONKAIGI_69,
  people=["岸田正義"], tags=["財政", "新庁舎", "学校施設"],
  title="累計645億円の借入見通し——「庁舎建設は一旦立ち止まるべき」",
  lead="新庁舎建設174億円、学校施設の長寿命化に10年で238.5億円。積み上がる将来負担に財政の見通しは立っているのか。岸田正義議員が一般質問で市長に迫った。",
  body="""
<h2 class="sec">数字で見る将来負担</h2>
<ul>
<li>新庁舎建設費：現行計画 <strong>174億円</strong>（資材高騰・中東情勢の影響は「注視し情報収集に努める」が予測は困難と市答弁）</li>
<li>学校施設長寿命化計画：今後10年間の建設費用 <strong>約238.5億円</strong>（うち起債 約182.9億円）</li>
<li>これらを合わせた将来の借入金は<strong>累計約645.7億円</strong>に達すると議員が提示</li>
</ul>
<h2 class="sec">市の回答</h2>
<p>新庁舎建設の事業者サウンディング調査には多くの事業者から申し込みがあり、7月中に結果を公表予定。起債額の増加は「大きな課題」と認識し、今後の財政計画のローリングで精査する意向を示したが、<strong>明確な財政見通しは示されなかった</strong>。</p>
<h2 class="sec">議員の主張</h2>
<p>岸田議員は、財政破綻への懸念から「庁舎建設は一旦立ち止まり、抜本的に見直すべきだ」と主張した。</p>
<h2 class="sec">あわせて読みたい</h2>
<p>同議員は同じ一般質問で、市民交流センターの指定管理委託料増額問題と公契約条例の制定も取り上げている（別記事「<a href="kouryu-center.html">市民交流センターの指定管理問題</a>」参照）。</p>
"""),

 dict(slug="gairoju", cat="本会議", date="2026-06-09", wareki="令和8年6月9日",
  src=["R8.6.9_本会議.html"], video=V_HONKAIGI_69,
  people=["渡辺大三"], tags=["環境・緑化", "都市計画"],
  title="桜4本、公園樹55本の伐採——「緑を増やして涼しい町を」の行方",
  lead="新小金井駅前の桜4本をはじめ、市内で予定される街路樹・公園樹の伐採。渡辺大三議員は補植の徹底と駅前緑化を求め、落葉苦情への「受忍義務」条例まで踏み込んだ。",
  body="""
<h2 class="sec">伐採の現状確認</h2>
<p>市内で予定されている街路樹の伐採（新小金井駅前の桜4本、公園樹55本など）の状況と理由を確認。伐採後の適切な補植と、<strong>街路樹総本数の維持・向上のための予算措置の徹底</strong>を要望した。</p>
<h2 class="sec">駅前の緑をどう増やすか</h2>
<p>武蔵小金井駅・東小金井駅・新小金井駅前の植栽の現状を指摘し、駅前空間の緑化推進に向けた具体的な検討と実行を求めた。</p>
<h2 class="sec">落葉の苦情と「受忍義務」</h2>
<p>落葉に対する市民の苦情がある中、中野区の条例にある「区民の受忍義務」のような規定の導入について市の見解を質問。市は安全性の確保、一部市民への負担集中、地域摩擦への懸念から慎重な姿勢を示す一方、<strong>緑の効用への理解を広める努力を続ける</strong>と答弁。議員は条例制定の検討を重ねて要望した。</p>
<h2 class="sec">コミュニティバスの運転士確保も</h2>
<p>同じ一般質問では、バス運転士不足への対応として、武蔵野市や東京都の確保策（住宅手当補助、採用広報補助、運転体験会補助など）を参考に市独自の取り組みを検討するよう提起。市は国・都への要望を継続しつつ、バスフェス等での情報発信を強化し、先進事例を注視すると答えた。</p>
"""),

 dict(slug="josei-kodomo", cat="本会議", date="2026-06-09", wareki="令和8年6月9日",
  src=["R8.6.9_本会議.html"], video=V_HONKAIGI_69,
  people=["片山かおる"], tags=["福祉", "子どもの権利", "教育"],
  title="女性支援法の活用と、子どもが自ら虐待を通報する権利",
  lead="「困難な問題を抱える女性支援法」を市はどう活かすか。そして増え続ける児童虐待通報の中で、子ども自身が SOS を出す方法は伝わっているか。片山かおる議員の一般質問。",
  body="""
<h2 class="sec">女性支援：26市の「情報非公開」を問う</h2>
<p>東京都23区と26市の女性支援法に関する調査結果の比較について市の見解を求め、<strong>26市の情報非公開が、必要な人に情報が届かない一因</strong>だとして是正を要望。江東区の組織改正による相談機能の連携強化や、世田谷区の若年女性の居場所「Uカフェ」を先進事例に挙げ、支援体制の充実、支援調整会議の設置検討、市民への情報周知、民間団体との協働を促した。市は庁内連携の強化、他自治体事例の研究、国・都への安全管理モデル・指針提示の要望の必要性を答弁した。</p>
<h2 class="sec">子どもの権利としての虐待通報</h2>
<ul>
<li>児童虐待の通報数は<strong>過去3年で増加傾向</strong>にある一方、子ども自身からの通報は少数にとどまる。</li>
<li>市は広報誌やキャンペーン等で周知していると答弁したが、議員は「子どもがSOSを出す<strong>具体的な方法</strong>を伝える教育」の必要性を強調。</li>
<li>「通報する権利があること」をあらゆる方法で子どもに伝えるよう要望し、男女平等と子どもの権利の関連からの権利学習の検討も求めた。</li>
</ul>
<h2 class="sec">教職員が萎縮しない主権者教育を</h2>
<p>教育基本法第16条の精神に基づき、教職員が萎縮せず主権者教育に取り組める環境づくりを要望。教育委員会は「不当な支配の禁止」を最重要原則とし、ドイツの政治教育3原則（ボイテルスバッハ・コンセンサス）が学習指導要領の精神と合致すると説明、多角的・多面的な議論を支援する姿勢を示した。</p>
"""),

 dict(slug="gikai-kaikaku", cat="議会運営委員会", date="2026-05-18", wareki="令和8年5月18日",
  src=["R8.5.18_議会運営委員会.html"], video=V_GIUN_518,
  people=["岸田正義", "片山かおる", "清水学", "坂井えつ子", "河野麻美", "水谷たかこ"], tags=["議会改革"],
  title="議会改革「3分の2で試行→全会一致で本格実施」ルールは是か非か",
  lead="全会一致が原則の議会改革を、3分の2の賛成で「試行」できるようにする——。合意形成のスピードを上げる提案に、会派の意見は真っ二つに割れた。5月18日の議会運営委員会から。",
  body="""
<h2 class="sec">提案の中身（7-13）</h2>
<p>議会改革の提案について、議員の3分の2が賛成すれば半年の試行期間とし、その後、改善点を議論して本格実施の可否を<strong>全会一致</strong>で決定する（条例改廃を要する案件は除外）。</p>
<h2 class="sec">賛否の構図</h2>
<table>
<tr><th>立場</th><th>主な主張</th></tr>
<tr><td>試行ルールに前向き</td><td>清水学議員・岸田正義議員・副議長：試行実施が議論を加速させ、課題解決や合意形成に有効</td></tr>
<tr><td>慎重・反対</td><td>令和新選組：全会一致ルールの継続を主張。片山かおる議員・委員長：試行も3分の2で強行される懸念、過去は議論で合意形成できており新ルールは不要</td></tr>
<tr><td>より広く賛成</td><td>参政党ほか：範囲制限も不要と賛成</td></tr>
</table>
<p>議論は平行線をたどり<strong>継続協議</strong>に。次回に向けて提案会派が試行実施の事例を調査・提出する。</p>
<h2 class="sec">同日に動いたその他の改革項目</h2>
<ul>
<li><strong>グループウェア連絡の確立（7-1）</strong>：メール併用を終了し主要な連絡手段とすることで一致。</li>
<li><strong>オンライン会議（7-4）</strong>：放送設備更新後のテスト会議を7月16日午前に実施することで合意。</li>
<li><strong>陳情・請願のオンライン提出（7-12）</strong>：意見がまとまらず「不一致」で協議終了。</li>
<li><strong>市議会誌の発行（7-14）</strong>：市政施行70周年（2028年）に向け継続協議。</li>
<li><strong>ペーパーレス化（7-2/7-3）</strong>・<strong>議会日程のゆとり（7-10）</strong>・<strong>視察のオンライン化（7-11）</strong>：いずれも継続協議。</li>
</ul>
"""),

 dict(slug="iran-bukka", cat="本会議", date="2026-06-09", wareki="令和8年6月9日",
  src=["R8.6.9_本会議.html"], video=V_HONKAIGI_69,
  people=["清水学", "水上洋志", "森戸よう子"], tags=["意見書", "経済・物価"],
  title="イラン戦争の物価高騰、市議会が国に緊急対策を求める——意見書可決",
  lead="イラン戦争に伴う物価高騰から暮らしと営業を守る緊急対策を求める意見書案第9号。政府対応は十分か不十分か、賛否の討論が交わされ、起立多数で可決された。",
  body="""
<h2 class="sec">討論：反対の立場から</h2>
<div class="quote"><span class="who">清水学議員（反対）</span>物価高騰対策の必要性は認めつつ、政府は既に国家原油の放出、3兆1千億円の補正予算の編成（予備費は機動的対応に必要）を実施。資材不足は過剰発注や流通の目詰まりが主因で、中小企業・雇用への資金繰り支援や価格転嫁要請など、総合的な対策を迅速に講じていると主張。</div>
<h2 class="sec">討論：賛成の立場から</h2>
<div class="quote"><span class="who">水上洋志議員（賛成）</span>イラン戦争による物価高と資材不足の深刻化を指摘し、政府補正予算は予備費が大半で不十分と批判。年金生活者や中小企業への踏み込んだ支援、石油関連製品の優先供給、大企業・富裕層への公正な課税を財源とすべきと訴えた。</div>
<h2 class="sec">採決</h2>
<p><strong>起立多数により原案可決</strong>。</p>
<h2 class="sec">市政への波及</h2>
<p>同日の一般質問では森戸よう子議員が、イラン戦争が引き起こす物価高騰・資材不足に対し、市発注工事や委託事業への影響の実態調査、資材確保や人件費高騰に苦しむ中小零細企業への支援、市民サービスへの影響回避を各課に指示するよう求めた。建設業者の切実な声や医療介護施設のアンケート結果も提示された。</p>
"""),

 dict(slug="kouryu-center", cat="本会議", date="2026-06-09", wareki="令和8年6月9日",
  src=["R8.6.9_本会議.html"], video=V_HONKAIGI_69,
  people=["岸田正義"], tags=["指定管理", "公契約", "文化施設"],
  title="市民交流センターの指定管理問題——委託料増額の裏で何が起きたか",
  lead="舞台会社との契約不成立が指定管理委託料の増額を招いた市民交流センター。2か月経っても進まない検証、明文化されない修繕計画。岸田正義議員が構造的な問題を追及し、公契約条例の制定へと議論をつないだ。",
  body="""
<h2 class="sec">何が問題になっているか</h2>
<ul>
<li>指定管理委託料の増額の原因となった<strong>舞台会社との契約不成立</strong>について、市の事実関係調査と責任の認識を追及。2か月以上経っても「慎重な協議」が行われておらず、募集要綱の改善も不十分と批判。</li>
<li>公募応募者の減少要因への対応の遅れを指摘。<strong>足立区の労働条件審査</strong>の導入や、選定委員による外部評価など再発防止の具体策を副市長に要求。副市長は課題解決の手法として認識し「研究検討を進める」と答弁。</li>
<li>舞台設備等が更新推奨年数を超過しているのに<strong>明文化された修繕計画がない</strong>ことを問題視し、早急な計画策定を要望。</li>
<li>「第2次芸術文化振興計画」の前期評価の遅延や推進委員会の議事録未公開を批判。コンセッション方式や、はけの森美術館との一体的運営の検討も提案した。</li>
</ul>
<h2 class="sec">公契約条例へ</h2>
<p>多摩地域で公契約条例の制定が進む中、小金井市が未制定である現状を批判。市が長年繰り返す懸念（最低賃金法との関係、費用対効果、労使への介入、実効性）は<strong>他市で既に乗り越えられている</strong>と指摘し、ヒアリングやアンケートを含む本格的な検討の開始を強く求めた。今回の委託料増額問題は、公契約における「適切な判断」が機能しなかった事例だとして条例の必要性を強調。市は研究検討を進める意向を示した。</p>
"""),
]

# =========================================================
# テンプレート
# =========================================================
BANNER = ('<div class="ai-banner"><span><b>非公式・AI生成コンテンツ。</b>'
          '原典（AI文字起こし・自動校正データ）をもとに自動編集・再構成したものです。'
          '要約・抽出に誤りを含む場合があります。正確な内容は原典・録画でご確認ください。</span></div>')

def shell(title, body, depth=0):
    rel = "../" * depth
    return f"""<!DOCTYPE html>
<html lang="ja"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700;900&display=swap">
<link rel="stylesheet" href="{rel}style.css">
</head><body>
<div class="topbar-line"></div>
{body}
<script src="{rel}video.js"></script>
</body></html>
"""

def headbar():
    return ('<div class="headbar"><div class="wrap">'
            '<a class="back" href="../index.html">← 一覧に戻る</a>'
            '<a class="bname" href="../index.html">小金井市議会 会議録ナレッジWiki</a>'
            '</div></div>')

def video_buttons(vids, label, jumps=0):
    if not vids: return ""
    btns = " ".join(f'<button class="watch" data-yt="{v}" data-title="{esc(label)}（動画{i}）">動画{i}を見る</button>'
                    for i, v in enumerate(vids, 1))
    note = f'<span class="vidnote">YouTube {len(vids)}本' + (f'・原典に頭出しリンク {jumps}か所' if jumps else "") + "</span>"
    return f'<div class="videorow">{btns}{note}</div>'

def footer(depth=0):
    return (f'<div class="footer">小金井市議会 会議録ナレッジWiki — 非公式・AI生成の二次編集版<br>'
            f'原典：<a href="{GIJI}/" target="_blank" rel="noopener">小金井市議会 非公式会議録（作成：ながとり太郎議員）</a>／'
            f'<a href="{YT_CH}" target="_blank" rel="noopener">市議会YouTube</a>／'
            f'<a href="{KENSAKU}" target="_blank" rel="noopener">公式会議録検索システム</a></div>')

def meeting_page(d):
    memhtml = ""
    if d["members"]:
        links = " ".join(f'<a class="chip" href="../p/{m}.html">{esc(m)}</a>' for m in d["members"])
        memhtml = f'<h2 class="sec">登壇した議員</h2><div class="chips">{links}</div>'
    billhtml = ""
    if d["bills"]:
        items = "".join(f"<li>{esc(b)}</li>" for b in d["bills"])
        billhtml = f'<h2 class="sec">議案・案件</h2><ul>{items}</ul>'
    content = d["summary_html"] or (
        f'<h2 class="sec">この会議について</h2>'
        f'<p>{esc(d["overview"]) if d["overview"] else "この会議録は全文の文字起こしと録画で構成されています。詳細は原典でご確認ください。"}</p>')
    body = f"""{headbar()}
<div class="wrap">
  <div class="crumb"><a href="../index.html">ホーム</a> › {esc(d["cat"])} › {esc(d["wareki"])}</div>
  {BANNER}
  <div class="doc">
    <p class="subtitle">{pill(d["cat"])} <span>{esc(d["wareki"])}</span>{' <span class="chip">要約あり</span>' if d["has_summary"] else ''}</p>
    <h1 class="title">{esc(d["type"])}</h1>
    {video_buttons(d["videos"], d["type"] + " " + d["wareki"], d["jumps"])}
    {content}
    {memhtml}
    {billhtml}
    <h2 class="sec">原典（全文・頭出しリンクつき）</h2>
    <p class="src">この会議の全文文字起こしと発言ごとの動画頭出しは原典でご覧いただけます。<br>
      原典：<a href="{GIJI}/{d['file']}" target="_blank" rel="noopener">{esc(d['file'])} ↗</a></p>
  </div>
  {footer()}
</div>
"""
    return shell(f"{d['type']} {d['wareki']}｜小金井市議会ナレッジWiki", body, depth=1)

def person_page(name, apps):
    apps = sorted(apps, key=lambda d: d["sortkey"], reverse=True)
    rows = "".join(
        f'<tr><td>{esc(d["wareki"])}</td><td>{pill(d["cat"])}</td>'
        f'<td><a href="../m/{d["file"]}">{esc(d["type"])}</a></td></tr>' for d in apps)
    arts = [a for a in ARTICLES if name in a["people"]]
    arthtml = ""
    if arts:
        items = "".join(f'<li><a href="../a/{a["slug"]}.html">{esc(a["title"])}</a></li>' for a in arts)
        arthtml = f'<h2 class="sec">関連する特集記事</h2><ul>{items}</ul>'
    body = f"""{headbar()}
<div class="wrap">
  <div class="crumb"><a href="../index.html">ホーム</a> › 議員 › {esc(name)}</div>
  {BANNER}
  <div class="doc">
    <p class="subtitle"><span class="chip">議員ページ（登壇記録）</span></p>
    <h1 class="title">{esc(name)} 議員</h1>
    <div class="chips"><span class="chip">登壇 {len(apps)} 会議</span></div>
    {arthtml}
    <h2 class="sec">登壇した会議</h2>
    <table><tr><th>日付</th><th>区分</th><th>会議</th></tr>{rows}</table>
    <p class="src">登壇記録は会議録の見出しから自動抽出したもので、抜けがある場合があります。</p>
  </div>
  {footer()}
</div>
"""
    return shell(f"{name} 議員｜小金井市議会ナレッジWiki", body, depth=1)

def article_page(a):
    srcs = "".join(
        f'<li><a href="../m/{f}">{esc(docs[f]["type"])}（{esc(docs[f]["wareki"])}）</a> ／ '
        f'<a href="{GIJI}/{f}" target="_blank" rel="noopener">原典 ↗</a></li>'
        for f in a["src"] if f in docs)
    ppl = " ".join(f'<a class="chip" href="../p/{p}.html">{esc(p)}</a>' for p in a["people"])
    tags = " ".join(f'<span class="chip">{esc(t)}</span>' for t in a["tags"])
    others = [x for x in ARTICLES if x["slug"] != a["slug"]][:3]
    rel = "".join(f'<li><a href="{x["slug"]}.html">{esc(x["title"])}</a></li>' for x in others)
    body = f"""{headbar()}
<div class="wrap">
  <div class="crumb"><a href="../index.html">ホーム</a> › 特集記事</div>
  {BANNER}
  <div class="doc">
    <p class="subtitle">{pill(a["cat"])} <span>{esc(a["wareki"])}</span> <span class="chip">特集記事</span></p>
    <h1 class="title">{esc(a["title"])}</h1>
    <p class="lead">{esc(a["lead"])}</p>
    <div class="videorow"><button class="watch" data-yt="{a["video"]}" data-title="{esc(a["title"])}">この会議の録画を見る</button></div>
    {a["body"]}
    <h2 class="sec">関係する議員</h2><div class="chips">{ppl}</div>
    <div class="chips">{tags}</div>
    <h2 class="sec">出典となった会議</h2><ul>{srcs}</ul>
    <h2 class="sec">ほかの特集記事</h2><ul>{rel}</ul>
    <p class="src">本記事は原典の要約データを再構成したものです。発言の正確な文脈は原典・録画でご確認ください。</p>
  </div>
  {footer()}
</div>
"""
    return shell(f"{a['title']}｜小金井市議会ナレッジWiki", body, depth=1)

# ---------- 書き出し：会議・議員・記事 ----------
for d in docs.values():
    open(os.path.join(OUT, "m", d["file"]), "w", encoding="utf-8").write(meeting_page(d))
for name, apps in people.items():
    open(os.path.join(OUT, "p", name + ".html"), "w", encoding="utf-8").write(person_page(name, apps))
for a in ARTICLES:
    open(os.path.join(OUT, "a", a["slug"] + ".html"), "w", encoding="utf-8").write(article_page(a))

# ---------- 検索インデックス ----------
search = [{"k": "m", "f": d["file"], "t": d["type"], "c": d["cat"], "d": d["iso"], "w": d["wareki"],
           "m": d["members"], "b": d["bills"][:8], "s": d["snippet"][:500], "v": len(d["videos"])}
          for d in sorted(docs.values(), key=lambda x: x["sortkey"], reverse=True)]
search += [{"k": "a", "f": a["slug"] + ".html", "t": a["title"], "c": a["cat"], "d": a["date"],
            "w": a["wareki"], "m": a["people"], "b": a["tags"],
            "s": a["lead"] + " " + collapse(strip_tags(a["body"]))[:400], "v": 1}
           for a in ARTICLES]
json.dump(search, open(os.path.join(OUT, "search.json"), "w", encoding="utf-8"), ensure_ascii=False)

# ---------- トップページ ----------
CATS = ["本会議", "常任委員会", "予算特別委員会", "議会運営委員会", "特別委員会・協議会"]
catcount = {c: sum(1 for d in docs.values() if d["cat"] == c) for c in CATS}
total_v = sum(len(d["videos"]) for d in docs.values())

facets = (f'<button class="facet is-active" data-cat="all"><span class="fdot" style="background:{DOT["all"]};"></span>'
          f'<span class="flabel">すべて</span><span class="fcnt">{len(docs)}</span></button>')
for c in CATS:
    facets += (f'<button class="facet" data-cat="{esc(c)}"><span class="fdot" style="background:{DOT[c]};"></span>'
               f'<span class="flabel">{esc(c)}</span><span class="fcnt">{catcount[c]}</span></button>')

SIDS = {n: f"s{i+1}" for i, (n, _) in enumerate(sessions)}
def sid(name): return SIDS[name]
jump = "".join(f'<a class="jump-item" href="#{sid(n)}"><span>{esc(n)}</span><span class="jump-cnt">{len(fs)}</span></a>'
               for n, fs in sessions)

acards = ""
for a in ARTICLES:
    acards += (f'<a class="acard" href="a/{a["slug"]}.html">{pill(a["cat"])}'
               f'<h3>{esc(a["title"])}</h3><p>{esc(a["lead"][:76])}…</p>'
               f'<span class="meta">{esc(a["wareki"])} ・ 特集記事</span></a>')

browse = ""
for name, files in sessions:
    entries = ""
    for f in files:
        if f not in docs: continue
        d = docs[f]
        entries += (f'<a class="entry" data-c="{esc(d["cat"])}" href="m/{f}">'
                    f'<span class="date">{esc(d["md"])}</span>{pill(d["cat"])}'
                    f'<span class="name">{esc(d["type"])}</span>'
                    f'<span class="sub">動画{len(d["videos"])}本</span><span class="chev">→</span></a>')
    browse += (f'<details class="session" open id="{sid(name)}"><summary class="session-head">'
               f'<span class="session-name">{esc(name)}</span><span class="session-count">{len(files)}</span>'
               f'<span class="session-chev">▾</span></summary><div class="entries">{entries}</div></details>')

people_sorted = sorted(people.items(), key=lambda kv: -len(kv[1]))
pchips = "".join(f'<a class="pchip" href="p/{n}.html">{esc(n)}<span class="cnt">{len(a)}</span></a>'
                 for n, a in people_sorted)

index_body = f"""
<div class="app">
<aside class="side">
  <div class="brand">
    <a href="index.html"><p class="kicker">小金井市議会</p><h1>会議録ナレッジWiki</h1></a>
    <p class="tag">非公式会議録アーカイブを、検索・議員・特集記事の切り口で横断できるように再編集したナレッジベースです。</p>
    <span class="nbadge">非公式・AI生成・二次編集</span>
  </div>
  <div class="side-search"><input id="q" type="search" placeholder="会議・議員・議案を検索" autocomplete="off"></div>
  <div>
    <h2>会議の種別</h2>
    <div class="facets">{facets}</div>
  </div>
  <div>
    <h2 class="jump-title">会期</h2>
    <nav class="jump">{jump}
      <a class="jump-item" href="#articles"><span>特集記事</span><span class="jump-cnt">{len(ARTICLES)}</span></a>
      <a class="jump-item" href="#people"><span>議員から探す</span><span class="jump-cnt">{len(people)}</span></a>
    </nav>
  </div>
  <div class="side-links">
    <a href="{GIJI}/" target="_blank" rel="noopener">原典アーカイブ<span class="arr">↗</span></a>
    <a href="{YT_CH}" target="_blank" rel="noopener">市議会YouTube<span class="arr">↗</span></a>
    <a href="{KENSAKU}" target="_blank" rel="noopener">公式会議録検索<span class="arr">↗</span></a>
    <p class="side-cred">原典：<a href="{GIJI}/" target="_blank" rel="noopener">小金井市議会 非公式会議録</a>（作成：ながとり太郎議員）をもとにAIが再編集。要約・抽出に誤りを含む場合があります。</p>
  </div>
</aside>
<main>
  <div class="main-head" id="articles"><h2>特集記事</h2>
    <span class="summary">審議の争点をAIが記事形式に再構成 <b>{len(ARTICLES)}</b>本</span></div>
  <div class="articles">{acards}</div>

  <div class="main-head"><h2>会議録一覧</h2>
    <span class="summary"><b>{len(docs)}</b>会議 ・ 動画<b>{total_v}</b>本 ・ 要約つき<b>{sum(d["has_summary"] for d in docs.values())}</b>件</span></div>
  <div id="results" class="hidden"></div>
  <div class="no-results hidden" id="noresults">該当する会議・記事が見つかりませんでした。</div>
  <div id="browse">{browse}</div>

  <div class="main-head" id="people"><h2>議員から探す</h2>
    <span class="summary">一般質問等の登壇記録から自動集約</span></div>
  <div class="people">{pchips}</div>

  <details class="about">
    <summary>この Wiki について<span class="s-chev">▾</span></summary>
    <div class="about-body">
      <p>本サイトは、<a href="{GIJI}/" target="_blank" rel="noopener">小金井市議会 非公式会議録</a>（ながとり太郎議員によるAI文字起こしアーカイブ）を原典として、
      AIが検索・議員・特集記事の切り口で再編集した非公式のナレッジベースです。</p>
      <ul>
        <li>要約・記事・抽出はAIによる自動生成のため、誤りを含む場合があります。</li>
        <li>正確な内容は、各ページからリンクしている原典（全文文字起こし・動画頭出しつき）および市議会の録画・公式会議録でご確認ください。</li>
        <li>会議の映像は<a href="{YT_CH}" target="_blank" rel="noopener">小金井市議会YouTubeチャンネル</a>から埋め込んでいます。</li>
      </ul>
    </div>
  </details>
  {footer()}
</main>
</div>
<script src="app.js"></script>
"""
open(os.path.join(OUT, "index.html"), "w", encoding="utf-8").write(
    shell("小金井市議会 会議録ナレッジWiki（非公式）", index_body))

print("WROTE:", OUT, "| meetings:", len(docs), "| people:", len(people), "| articles:", len(ARTICLES))
