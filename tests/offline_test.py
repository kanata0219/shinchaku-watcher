"""
offline_test.py - ネットワーク非依存のロジック検証。
実サイトと同じ構造のfixtureを使い、エンジンの中核(フィード/一覧抽出・
重複排除・新着→既知の遷移・ハッシュ差分・出力生成)を確認する。
"""
import sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from watcher.sources import collect_feed, collect_listing, collect_hash
from watcher.store import Store
from watcher import report

# ---- 実サイトと同じ構造の fixture ----
ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
 <title>Winds Score 新着商品</title>
 <entry><title>津軽海峡・冬景色〔Grade 2（小編成）〕</title>
   <link rel="alternate" href="https://winds-score.com/products/sbl-00156"/>
   <published>2026-10-02T00:00:00+09:00</published>
   <updated>2026-10-02T00:00:00+09:00</updated></entry>
 <entry><title>F・L・Y〔Grade 3〕</title>
   <link rel="alternate" href="https://winds-score.com/products/wsl-00302"/>
   <published>2026-10-02T00:00:00+09:00</published></entry>
 <entry><title>津軽海峡・冬景色〔Grade 3〕</title>
   <link rel="alternate" href="https://winds-score.com/products/wsl-00304"/>
   <published>2026-10-02T00:00:00+09:00</published></entry>
</feed>"""

MUSIC8_V1 = """<html><body><table>
<tr><td>2026/10/08</td><td><a href="/products/detail211802.php">パッヘルベルのカノン（2026年編曲）</a></td></tr>
<tr><td>2026/10/08</td><td><a href="/products/detail212304.php">津軽海峡・冬景色</a></td></tr>
<tr><td>2026/10/07</td><td><a href="/products/detail211666.php">夜の踊り子【フルート ソロ】</a></td></tr>
<tr><td><a href="/company/about.php">会社概要</a></td></tr>
</table></body></html>"""

# 2回目: 先頭に新商品が1件追加された想定
MUSIC8_V2 = MUSIC8_V1.replace(
  '<tr><td>2026/10/08</td><td><a href="/products/detail211802.php">',
  '<tr><td>2026/10/09</td><td><a href="/products/detail299999.php">新曲サンプル・マーチ</a></td></tr>'
  '<tr><td>2026/10/08</td><td><a href="/products/detail211802.php">')

BRAIN = """<html><body>
<a href="/shop/g/gPG-THB26/">【数量限定】第69回東北吹奏楽コンクール 公式プログラム</a>
<a href="/shop/g/gOSBR-42168/">【CD】武蔵野音楽大学ウィンドアンサンブル Vol.28</a>
<a href="/shop/c/c10/">カテゴリ: 吹奏楽</a>
</body></html>"""

HASHPAGE_V1 = "<html><body><main>新着: A, B, C</main></body></html>"
HASHPAGE_V2 = "<html><body><main>新着: A, B, C, D</main></body></html>"


class FakeFetcher:
    def __init__(self, mapping): self.mapping = mapping
    def get(self, url, **kw):
        if url in self.mapping:
            return {"ok": True, "status": 200, "text": self.mapping[url],
                    "from_cache": False, "error": None}
        return {"ok": False, "status": 404, "text": None,
                "from_cache": False, "error": "HTTP 404"}


def main():
    tmp = Path(tempfile.mkdtemp())
    store = Store(tmp / "t.db")
    passed = []

    def check(cond, msg):
        passed.append(cond)
        print(("  OK  " if cond else "  NG  ") + msg)

    # 1) フィード抽出
    ff = FakeFetcher({"atom": ATOM})
    r = collect_feed({"id": "ws", "name": "ウィンズスコア", "url": "atom"}, ff)
    check(r.ok and len(r.items) == 3, f"feed: 3件抽出 (実際 {len(r.items)})")
    check(r.items[0].title.startswith("津軽海峡"), "feed: タイトル取得")
    check(r.items[0].published_at.startswith("2026-10-02"), "feed: 公開日取得")

    # 2) 一覧抽出(正規表現パターン): 商品3件、会社概要リンクは除外
    fm = FakeFetcher({"m8": MUSIC8_V1})
    r = collect_listing({"id": "m8", "name": "ミュージックエイト", "url": "m8",
                         "item_link_pattern": r"/products/detail\d+\.php"}, fm)
    check(r.ok and len(r.items) == 3, f"listing(regex): 3件抽出・非商品除外 (実際 {len(r.items)})")

    # 3) brain パターン
    fb = FakeFetcher({"b": BRAIN})
    r = collect_listing({"id": "b", "name": "ブレーン", "url": "b",
                         "item_link_pattern": r"/shop/g/g[\w\-]+/?$"}, fb)
    check(r.ok and len(r.items) == 2, f"listing: brain 2件・カテゴリ除外 (実際 {len(r.items)})")

    # 4) 新着→既知の遷移: 1回目は全件新着
    r1 = collect_listing({"id": "m8", "name": "ミュージックエイト", "url": "m8",
                          "item_link_pattern": r"/products/detail\d+\.php"}, fm)
    new1 = store.upsert_items(r1.items)
    check(len(new1) == 3, f"1回目: 全件新着 (実際 {len(new1)})")

    # 5) 同じ内容で2回目 → 新着0 (重複排除)
    new2 = store.upsert_items(r1.items)
    check(len(new2) == 0, f"2回目同一: 新着0 (実際 {len(new2)})")

    # 6) 1件追加された3回目 → 新着1だけ
    fm2 = FakeFetcher({"m8": MUSIC8_V2})
    r3 = collect_listing({"id": "m8", "name": "ミュージックエイト", "url": "m8",
                          "item_link_pattern": r"/products/detail\d+\.php"}, fm2)
    new3 = store.upsert_items(r3.items)
    check(len(new3) == 1 and new3[0][1].title.startswith("新曲"),
          f"追加後: 新着1だけ (実際 {len(new3)})")

    # 7) ハッシュ差分: 初回=基準, 同一=変化なし, 変更=1件
    fh = FakeFetcher({"h": HASHPAGE_V1})
    rh1 = collect_hash({"id": "h", "name": "××社", "url": "h", "content_selector": "main"}, fh, store)
    check(rh1.ok and len(rh1.items) == 0, "hash: 初回は基準記録(新着0)")
    rh2 = collect_hash({"id": "h", "name": "××社", "url": "h", "content_selector": "main"}, fh, store)
    check(len(rh2.items) == 0, "hash: 変化なしは新着0")
    fh2 = FakeFetcher({"h": HASHPAGE_V2})
    rh3 = collect_hash({"id": "h", "name": "××社", "url": "h", "content_selector": "main"}, fh2, store)
    check(len(rh3.items) == 1, "hash: 変化を検知(1件)")

    # 8) 壊れ検知: 2回連続0件で consecutive_empty が増える
    store.update_health("empty", "空社", ok=True, item_count=0, error=None, note="")
    store.update_health("empty", "空社", ok=True, item_count=0, error=None, note="")
    h = [x for x in store.health_rows() if x["publisher_id"] == "empty"][0]
    check(h["consecutive_empty"] == 2, f"壊れ検知: 連続空=2 (実際 {h['consecutive_empty']})")

    # 9) 出力生成
    store.record_run("2026-10-07T09:00:00+09:00", 3, 0, 4)
    out = tmp / "public"; out.mkdir()
    report.write_json(store, out / "new_items.json")
    report.render_dashboard(store, out / "index.html")
    n = report.render_digest(store, out / "digest.html",
                             date_str=new3[0][1] and None)
    dash = (out / "index.html").read_text(encoding="utf-8")
    check((out / "new_items.json").stat().st_size > 0, "出力: new_items.json 生成")
    check("ダッシュボード" in dash and "ミュージックエイト" in dash, "出力: ダッシュボードに内容反映")

    store.close()
    print(f"\n結果: {sum(passed)}/{len(passed)} 合格")
    return 0 if all(passed) else 1

if __name__ == "__main__":
    raise SystemExit(main())
