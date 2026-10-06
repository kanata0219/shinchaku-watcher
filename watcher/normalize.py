"""
normalize.py - URL・タイトルの正規化と、重複排除キーの生成。

同じ商品が別URL(トラッキングパラメータ付き等)で現れても一件として扱えるように、
URLとタイトルを正規化して安定した一意キーを作る。
"""
import hashlib
import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

# 除去するトラッキング系クエリパラメータ
_DROP_QUERY_PREFIXES = ("utm_",)
_DROP_QUERY_KEYS = {
    "fbclid", "gclid", "yclid", "mc_cid", "mc_eid",
    "ref", "ref_", "_ga", "cx", "ie", "oe",
}


def normalize_url(url: str) -> str:
    """URLを正規化する。
    - scheme/host を小文字化
    - fragment(#...) を除去
    - トラッキングパラメータを除去
    - 末尾スラッシュの有無は保持(サイトによって意味が違うため触らない)
    """
    if not url:
        return ""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip()

    scheme = (parts.scheme or "https").lower()
    netloc = parts.netloc.lower()

    kept = []
    for k, v in parse_qsl(parts.query, keep_blank_values=False):
        kl = k.lower()
        if kl in _DROP_QUERY_KEYS:
            continue
        if any(kl.startswith(p) for p in _DROP_QUERY_PREFIXES):
            continue
        kept.append((k, v))
    query = urlencode(kept)

    return urlunsplit((scheme, netloc, parts.path, query, ""))


def normalize_title(s: str) -> str:
    """タイトルを正規化する。
    - NFKC で全角/半角・互換文字をそろえる
    - 連続する空白を1つに畳む
    - 前後の空白・記号ノイズを除去
    """
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("　", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def item_key(publisher_id: str, url: str, title: str) -> str:
    """アイテムの一意キー。URLがあればURL優先、無ければ出版社+タイトル。"""
    nurl = normalize_url(url)
    if nurl:
        basis = f"url::{nurl}"
    else:
        basis = f"title::{publisher_id}::{normalize_title(title)}"
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()


def text_hash(s: str) -> str:
    """ページ主要部テキストのハッシュ(差分検知用)。"""
    norm = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s or "")).strip()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()
