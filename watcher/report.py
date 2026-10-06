"""
report.py - 出力(管理ダッシュボード / 日次ダイジェスト / JSON)の生成。

- new_items.json : 直近の新着データ(比較検索サイト等が後で読める素材)
- index.html     : 管理ダッシュボード(新着一覧 + 各サイトの稼働状況)
- digest.html    : その日の新着ダイジェスト

配色は既存SPAと同じ 白 × 濃緑 のテーマ。ライト/ダーク両対応。
"""
import html
import json
from datetime import datetime

GREEN = "#1f6b4a"
GREEN_DARK = "#12402d"


def _esc(s):
    return html.escape(str(s or ""))


def write_json(store, path, limit=500):
    items = store.recent_items(limit=limit)
    payload = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "total": store.total_items(),
        "items": [
            {
                "publisher": it["publisher_name"],
                "publisher_id": it["publisher_id"],
                "title": it["title"],
                "url": it["url"],
                "published_at": it["published_at"],
                "first_seen": it["first_seen"],
                "method": it["method"],
            } for it in items
        ],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


_BASE_CSS = f"""
:root {{
  --green: {GREEN}; --green-dark: {GREEN_DARK};
  --bg: #f6f8f6; --card: #ffffff; --text: #1a2420;
  --muted: #5d6b63; --border: #d9e2dc; --warn-bg: #fff4e5; --warn: #9a5b00;
  --bad-bg: #fde8e8; --bad: #9b1c1c; --ok: #1f6b4a;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --bg: #0f1613; --card: #16211c; --text: #e7efe9;
    --muted: #9fb0a7; --border: #26362e; --warn-bg: #3a2c12; --warn: #ffcf7a;
    --bad-bg: #3a1a1a; --bad: #ff9b9b; --ok: #6fd3a2; --green: #2f9c6e;
  }}
}}
* {{ box-sizing: border-box; }}
body {{ margin:0; background:var(--bg); color:var(--text);
  font-family: system-ui, -apple-system, "Hiragino Kaku Gothic ProN",
  "Noto Sans JP", Meiryo, sans-serif; line-height:1.6; }}
header {{ background:var(--green); color:#fff; padding:20px 16px; }}
header .wrap, main {{ max-width: 980px; margin:0 auto; }}
main {{ padding:16px; }}
h1 {{ margin:0; font-size:1.3rem; }}
.sub {{ opacity:.85; font-size:.85rem; margin-top:4px; }}
.cards {{ display:flex; gap:12px; flex-wrap:wrap; margin:16px 0; }}
.stat {{ background:var(--card); border:1px solid var(--border);
  border-radius:12px; padding:14px 18px; flex:1; min-width:140px; }}
.stat b {{ display:block; font-size:1.6rem; color:var(--green); }}
.stat span {{ color:var(--muted); font-size:.8rem; }}
h2 {{ font-size:1.05rem; border-left:4px solid var(--green);
  padding-left:10px; margin:28px 0 10px; }}
.pub {{ margin:18px 0; }}
.pub h3 {{ font-size:.95rem; margin:0 0 6px; color:var(--green-dark); }}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) .pub h3 {{ color: var(--ok); }}
}}
ul.items {{ list-style:none; margin:0; padding:0;
  background:var(--card); border:1px solid var(--border); border-radius:12px; }}
ul.items li {{ padding:10px 14px; border-top:1px solid var(--border); }}
ul.items li:first-child {{ border-top:none; }}
ul.items a {{ color:var(--text); text-decoration:none; font-weight:600; }}
ul.items a:hover {{ text-decoration:underline; color:var(--green); }}
.meta {{ color:var(--muted); font-size:.78rem; margin-top:2px; }}
.badge {{ display:inline-block; font-size:.7rem; padding:1px 7px;
  border-radius:999px; border:1px solid var(--border); color:var(--muted); }}
table {{ width:100%; border-collapse:collapse; background:var(--card);
  border:1px solid var(--border); border-radius:12px; overflow:hidden;
  font-size:.85rem; }}
th, td {{ text-align:left; padding:8px 12px; border-top:1px solid var(--border); }}
th {{ background:var(--green); color:#fff; }}
.pill {{ padding:2px 8px; border-radius:999px; font-size:.75rem; font-weight:600; }}
.pill.ok {{ color:var(--ok); }}
.pill.warn {{ background:var(--warn-bg); color:var(--warn); }}
.pill.bad {{ background:var(--bad-bg); color:var(--bad); }}
footer {{ color:var(--muted); font-size:.78rem; text-align:center;
  padding:24px 16px; }}
.empty {{ color:var(--muted); padding:14px; background:var(--card);
  border:1px dashed var(--border); border-radius:12px; }}
"""


def _page(title, body):
    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow, noarchive, noimageindex">
<title>{_esc(title)}</title>
<style>{_BASE_CSS}</style></head>
<body>{body}
<footer>shinchaku-watcher · 吹奏楽譜 新着監視システム</footer>
</body></html>"""


def _item_li(it, show_pub=False):
    pub = f'<span class="badge">{_esc(it["publisher_name"])}</span> ' if show_pub else ""
    pubdate = _esc(it["published_at"][:10]) if it.get("published_at") else ""
    first = _esc(it["first_seen"][:10])
    meta = f'検知 {first}'
    if pubdate:
        meta += f' · 公開 {pubdate}'
    meta += f' · {_esc(it["method"])}'
    return (f'<li><a href="{_esc(it["url"])}" target="_blank" '
            f'rel="noopener">{pub}{_esc(it["title"])}</a>'
            f'<div class="meta">{meta}</div></li>')


def render_dashboard(store, path, max_new=200):
    last = store.last_run()
    last_time = _esc(last["finished_at"][:16].replace("T", " ")) if last else "—"
    total = store.total_items()
    recent = store.recent_items(limit=max_new)
    health = store.health_rows()

    # 新着を出版社ごとにまとめる(直近分)
    by_pub = {}
    for it in recent:
        by_pub.setdefault(it["publisher_name"], []).append(it)

    # 稼働状況サマリ
    n_ok = sum(1 for h in health if h["last_error"] is None)
    n_bad = sum(1 for h in health if h["last_error"])
    n_warn = sum(1 for h in health
                 if h["last_error"] is None and h["consecutive_empty"] >= 2)

    body = [f"""<header><div class="wrap">
      <h1>新着楽譜ダッシュボード</h1>
      <div class="sub">最終実行: {last_time}</div></div></header><main>"""]

    body.append(f"""<div class="cards">
      <div class="stat"><b>{total}</b><span>累計検知アイテム</span></div>
      <div class="stat"><b>{len(health)}</b><span>監視サイト数</span></div>
      <div class="stat"><b>{n_ok}</b><span>正常</span></div>
      <div class="stat"><b>{n_warn + n_bad}</b><span>要確認</span></div>
    </div>""")

    # 稼働状況(壊れ検知)
    body.append("<h2>サイト稼働状況</h2>")
    if health:
        rows = []
        for h in health:
            if h["last_error"]:
                st = f'<span class="pill bad">エラー</span>'
            elif h["consecutive_empty"] >= 2:
                st = f'<span class="pill warn">要確認</span>'
            else:
                st = f'<span class="pill ok">正常</span>'
            detail = _esc(h["last_error"] or h["note"] or "")
            lastok = _esc((h["last_ok"] or "")[:16].replace("T", " "))
            rows.append(
                f"<tr><td>{_esc(h['publisher_name'])}</td><td>{st}</td>"
                f"<td>{h['last_item_count']}</td><td>{lastok}</td>"
                f"<td>{detail}</td></tr>")
        body.append(
            "<table><tr><th>出版社</th><th>状態</th><th>取得件数</th>"
            "<th>最終成功</th><th>備考</th></tr>" + "".join(rows) + "</table>")
    else:
        body.append('<div class="empty">まだ実行されていません。</div>')

    # 新着一覧
    body.append("<h2>新着一覧(直近)</h2>")
    if by_pub:
        for pub, items in by_pub.items():
            body.append(f'<div class="pub"><h3>{_esc(pub)}（{len(items)}）</h3>'
                        '<ul class="items">'
                        + "".join(_item_li(it) for it in items)
                        + "</ul></div>")
    else:
        body.append('<div class="empty">まだ新着データがありません。</div>')

    body.append("</main>")
    with open(path, "w", encoding="utf-8") as f:
        f.write(_page("新着楽譜ダッシュボード", "".join(body)))


def render_digest(store, path, date_str=None):
    if date_str is None:
        date_str = datetime.now().astimezone().strftime("%Y-%m-%d")
    items = store.items_first_seen_on(date_str)

    body = [f"""<header><div class="wrap">
      <h1>新着ダイジェスト</h1>
      <div class="sub">{_esc(date_str)} に初めて検知した楽譜 · {len(items)}件</div>
      </div></header><main>"""]
    if items:
        body.append('<ul class="items">'
                    + "".join(_item_li(it, show_pub=True) for it in items)
                    + "</ul>")
    else:
        body.append('<div class="empty">本日の新着はありません。</div>')
    body.append("</main>")
    with open(path, "w", encoding="utf-8") as f:
        f.write(_page(f"新着ダイジェスト {date_str}", "".join(body)))
    return len(items)
