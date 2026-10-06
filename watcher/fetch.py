"""
fetch.py - 礼儀正しいHTTP取得。

- robots.txt を尊重(サイト単位で無効化も可能)
- 条件付きGET(ETag / Last-Modified)で無駄な転送を避け、304なら前回本文を使う
- ホスト単位のレート制限と、指数バックオフのリトライ
- キャッシュは data/cache 以下にファイルで保持

低頻度(1日1回)・低負荷の個人監視を前提にしているが、相手サイトに迷惑を
かけないことを最優先にしている。
"""
import json
import time
import hashlib
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import requests

DEFAULT_UA = (
    "shinchaku-watcher/0.1 (band sheet-music new-arrivals monitor; "
    "contact: set via config user_agent)"
)


class Fetcher:
    def __init__(self, cache_dir, user_agent=DEFAULT_UA,
                 obey_robots=True, timeout=20, default_rate_limit=2.0):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.user_agent = user_agent
        self.obey_robots = obey_robots
        self.timeout = timeout
        self.default_rate_limit = default_rate_limit

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent,
                                     "Accept-Language": "ja,en;q=0.8"})
        self._robots = {}          # host -> RobotFileParser or None
        self._last_request = {}    # host -> timestamp

    # ---- robots ----
    def _robots_ok(self, url) -> bool:
        if not self.obey_robots:
            return True
        host = urlsplit(url).netloc
        if host not in self._robots:
            rp = RobotFileParser()
            robots_url = f"{urlsplit(url).scheme}://{host}/robots.txt"
            try:
                resp = self.session.get(robots_url, timeout=self.timeout)
                if resp.status_code >= 400:
                    rp = None  # robots.txt が無い/取れない → 許可とみなす
                else:
                    rp.parse(resp.text.splitlines())
            except Exception:
                rp = None
            self._robots[host] = rp
        rp = self._robots[host]
        if rp is None:
            return True
        return rp.can_fetch(self.user_agent, url)

    # ---- rate limit ----
    def _throttle(self, url, rate_limit):
        host = urlsplit(url).netloc
        wait = rate_limit if rate_limit is not None else self.default_rate_limit
        last = self._last_request.get(host)
        if last is not None:
            elapsed = time.time() - last
            if elapsed < wait:
                time.sleep(wait - elapsed)
        self._last_request[host] = time.time()

    # ---- cache ----
    def _cache_path(self, url):
        h = hashlib.sha1(url.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{h}.json"

    def _load_cache(self, url):
        p = self._cache_path(url)
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                return None
        return None

    def _save_cache(self, url, etag, last_modified, body):
        p = self._cache_path(url)
        p.write_text(json.dumps({
            "url": url, "etag": etag, "last_modified": last_modified,
            "body": body, "saved_at": time.time(),
        }, ensure_ascii=False), encoding="utf-8")

    # ---- main ----
    def get(self, url, rate_limit=None, retries=3, backoff=2.0):
        """URLを取得して本文テキストを返す。
        戻り値: dict(ok, status, text, from_cache, error)
        """
        if not self._robots_ok(url):
            return {"ok": False, "status": None, "text": None,
                    "from_cache": False, "error": "robots.txt disallow"}

        cache = self._load_cache(url)
        headers = {}
        if cache:
            if cache.get("etag"):
                headers["If-None-Match"] = cache["etag"]
            if cache.get("last_modified"):
                headers["If-Modified-Since"] = cache["last_modified"]

        last_err = None
        for attempt in range(retries):
            self._throttle(url, rate_limit)
            try:
                resp = self.session.get(url, headers=headers,
                                        timeout=self.timeout)
            except requests.RequestException as e:
                last_err = str(e)
                time.sleep(backoff * (attempt + 1))
                continue

            if resp.status_code == 304 and cache:
                return {"ok": True, "status": 304, "text": cache["body"],
                        "from_cache": True, "error": None}

            if resp.status_code == 200:
                resp.encoding = resp.encoding or resp.apparent_encoding
                body = resp.text
                self._save_cache(url, resp.headers.get("ETag"),
                                 resp.headers.get("Last-Modified"), body)
                return {"ok": True, "status": 200, "text": body,
                        "from_cache": False, "error": None}

            if resp.status_code in (429, 500, 502, 503, 504):
                last_err = f"HTTP {resp.status_code}"
                time.sleep(backoff * (attempt + 1))
                continue

            # その他(403,404 等)はリトライしない
            return {"ok": False, "status": resp.status_code, "text": None,
                    "from_cache": False, "error": f"HTTP {resp.status_code}"}

        return {"ok": False, "status": None, "text": None,
                "from_cache": False, "error": last_err or "failed"}
