"""
sources.py - 階層型の取得アダプタ。

site設定(registry.yamlの1エントリ)とFetcherを受け取り、
新着アイテムのリストを返す。methodごとに取得方法を切り替える。

    feed    : RSS/Atom をfeedparserで解析
    listing : 新着ページをBeautifulSoupで解析し、
              商品リンクの正規表現(item_link_pattern)で抽出
    hash    : ページ主要部のテキストハッシュを前回と比較(差分検知)

いずれも返すのは Item のリスト。取れなかった/壊れた場合は例外ではなく
空リスト + エラー情報(collectの戻り値)で扱い、1サイトの失敗が全体を
止めないようにする。
"""
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urljoin

import feedparser
from bs4 import BeautifulSoup

from .normalize import normalize_title, text_hash


@dataclass
class Item:
    publisher_id: str
    publisher_name: str
    title: str
    url: str
    published_at: str = ""     # ISO文字列(フィードにあれば)。無ければ空
    price: str = ""            # 任意(将来のフルメタデータ用)
    method: str = ""


@dataclass
class CollectResult:
    ok: bool
    items: list = field(default_factory=list)
    error: str = ""
    note: str = ""


def _now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat()


# ------------------------------------------------------------------ feed
def collect_feed(site, fetcher):
    url = site["url"]
    res = fetcher.get(url, rate_limit=site.get("rate_limit_sec"))
    if not res["ok"]:
        return CollectResult(False, error=res["error"])

    parsed = feedparser.parse(res["text"])
    items = []
    max_items = site.get("max_items", 50)
    for entry in parsed.entries[:max_items]:
        title = normalize_title(entry.get("title", ""))
        link = entry.get("link", "")
        pub = ""
        for key in ("published", "updated", "pubDate"):
            if entry.get(key):
                pub = entry.get(key)
                break
        if title and link:
            items.append(Item(site["id"], site["name"], title, link,
                              published_at=pub, method="feed"))
    note = "" if items else "フィードにエントリが無い(壊れの可能性)"
    return CollectResult(True, items=items, note=note)


# --------------------------------------------------------------- listing
def collect_listing(site, fetcher):
    url = site["url"]
    res = fetcher.get(url, rate_limit=site.get("rate_limit_sec"))
    if not res["ok"]:
        return CollectResult(False, error=res["error"])

    soup = BeautifulSoup(res["text"], "lxml")

    # 抽出範囲を絞る(任意)
    scope = soup
    container = site.get("container_selector")
    if container:
        node = soup.select_one(container)
        if node is not None:
            scope = node

    pattern = site.get("item_link_pattern")
    max_items = site.get("max_items", 50)
    items = []
    seen = set()

    if pattern:
        rx = re.compile(pattern)
        for a in scope.find_all("a", href=True):
            href = a["href"]
            if not rx.search(href):
                continue
            full = urljoin(url, href)
            if full in seen:
                continue
            title = normalize_title(a.get_text(" ", strip=True))
            if not title:
                # アンカーにテキストが無い場合、img alt や title属性を試す
                img = a.find("img")
                if img and img.get("alt"):
                    title = normalize_title(img["alt"])
                elif a.get("title"):
                    title = normalize_title(a["title"])
            if not title:
                continue
            seen.add(full)
            items.append(Item(site["id"], site["name"], title, full,
                              method="listing"))
            if len(items) >= max_items:
                break
    else:
        # パターン未指定: item_selector + title/link セレクタ方式
        item_sel = site.get("item_selector")
        if not item_sel:
            return CollectResult(False,
                error="listing には item_link_pattern か item_selector が必要")
        for block in scope.select(item_sel)[:max_items]:
            a = (block.select_one(site["link_selector"])
                 if site.get("link_selector") else block.find("a", href=True))
            if not a or not a.get("href"):
                continue
            full = urljoin(url, a["href"])
            if full in seen:
                continue
            if site.get("title_selector"):
                tnode = block.select_one(site["title_selector"])
                title = normalize_title(tnode.get_text(" ", strip=True)) if tnode else ""
            else:
                title = normalize_title(a.get_text(" ", strip=True))
            if not title:
                continue
            seen.add(full)
            items.append(Item(site["id"], site["name"], title, full,
                              method="listing"))

    note = "" if items else "新着を1件も抽出できない(壊れ/セレクタ要確認)"
    return CollectResult(True, items=items, note=note)


# ------------------------------------------------------------------ hash
def collect_hash(site, fetcher, store):
    """ページ主要部のハッシュ差分。変化を検知したら合成アイテムを1件返す。
    正確な新着内容は取れないが「動いた」ことは確実に検知でき、人が確認に行ける。
    """
    url = site["url"]
    res = fetcher.get(url, rate_limit=site.get("rate_limit_sec"))
    if not res["ok"]:
        return CollectResult(False, error=res["error"])

    soup = BeautifulSoup(res["text"], "lxml")
    sel = site.get("content_selector")
    node = soup.select_one(sel) if sel else (soup.body or soup)
    content = node.get_text(" ", strip=True) if node else ""
    h = text_hash(content)

    prev = store.get_page_hash(url)
    store.set_page_hash(url, h)

    if prev is None:
        return CollectResult(True, items=[], note="初回ハッシュ記録(基準確定)")
    if prev == h:
        return CollectResult(True, items=[], note="変化なし")

    # 変化あり
    title = f"ページ更新を検知({datetime.now().strftime('%Y-%m-%d %H:%M')})"
    item = Item(site["id"], site["name"], title, url,
                published_at=_now_iso(), method="hash")
    return CollectResult(True, items=[item], note="差分検知: 内容を要確認")


# ---------------------------------------------------------------- dispatch
def collect(site, fetcher, store):
    method = site.get("method", "listing")
    if method == "feed":
        return collect_feed(site, fetcher)
    if method == "listing":
        return collect_listing(site, fetcher)
    if method == "hash":
        return collect_hash(site, fetcher, store)
    return CollectResult(False, error=f"未知のmethod: {method}")
