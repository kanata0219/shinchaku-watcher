"""
store.py - SQLiteによる状態保存。

- items     : 検知した楽譜(初回検知日 first_seen で「新着」を判定)
- page_state: hash差分用のページハッシュ
- site_health: 各サイトの稼働状況(壊れ検知)
- runs      : 実行履歴

GitHub Actionsは実行ごとに環境が消えるため、このDBファイルをリポジトリに
コミットして状態を引き継ぐ(README参照)。
"""
import sqlite3
from datetime import datetime, timezone

from .normalize import item_key


def _now():
    return datetime.now(timezone.utc).astimezone().isoformat()


SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    key           TEXT PRIMARY KEY,
    publisher_id  TEXT NOT NULL,
    publisher_name TEXT,
    title         TEXT,
    url           TEXT,
    published_at  TEXT,
    price         TEXT,
    method        TEXT,
    first_seen    TEXT NOT NULL,
    last_seen     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_items_pub ON items(publisher_id);
CREATE INDEX IF NOT EXISTS idx_items_first ON items(first_seen);

CREATE TABLE IF NOT EXISTS page_state (
    url          TEXT PRIMARY KEY,
    content_hash TEXT,
    updated_at   TEXT
);

CREATE TABLE IF NOT EXISTS site_health (
    publisher_id      TEXT PRIMARY KEY,
    publisher_name    TEXT,
    last_run          TEXT,
    last_ok           TEXT,
    last_item_count   INTEGER DEFAULT 0,
    consecutive_empty INTEGER DEFAULT 0,
    last_error        TEXT,
    note              TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at  TEXT,
    finished_at TEXT,
    sites_ok    INTEGER,
    sites_failed INTEGER,
    new_count   INTEGER
);
"""


class Store:
    def __init__(self, db_path):
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self):
        self.conn.close()

    # ---- items ----
    def upsert_items(self, items):
        """アイテム群を保存し、今回初めて見たもの(新着)のリストを返す。"""
        now = _now()
        new_items = []
        for it in items:
            key = item_key(it.publisher_id, it.url, it.title)
            row = self.conn.execute(
                "SELECT key FROM items WHERE key = ?", (key,)).fetchone()
            if row is None:
                self.conn.execute(
                    """INSERT INTO items
                       (key, publisher_id, publisher_name, title, url,
                        published_at, price, method, first_seen, last_seen)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (key, it.publisher_id, it.publisher_name, it.title, it.url,
                     it.published_at, it.price, it.method, now, now))
                new_items.append((key, it))
            else:
                self.conn.execute(
                    "UPDATE items SET last_seen = ? WHERE key = ?", (now, key))
        self.conn.commit()
        return new_items

    def recent_items(self, limit=300):
        cur = self.conn.execute(
            """SELECT * FROM items
               ORDER BY first_seen DESC, rowid DESC LIMIT ?""", (limit,))
        return [dict(r) for r in cur.fetchall()]

    def items_first_seen_on(self, date_str):
        """first_seen が指定日(YYYY-MM-DD)のアイテム。"""
        cur = self.conn.execute(
            "SELECT * FROM items WHERE substr(first_seen,1,10) = ? "
            "ORDER BY publisher_name, first_seen", (date_str,))
        return [dict(r) for r in cur.fetchall()]

    def total_items(self):
        return self.conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]

    # ---- page hash ----
    def get_page_hash(self, url):
        row = self.conn.execute(
            "SELECT content_hash FROM page_state WHERE url = ?", (url,)).fetchone()
        return row["content_hash"] if row else None

    def set_page_hash(self, url, h):
        self.conn.execute(
            """INSERT INTO page_state(url, content_hash, updated_at)
               VALUES (?,?,?)
               ON CONFLICT(url) DO UPDATE SET content_hash=excluded.content_hash,
                                              updated_at=excluded.updated_at""",
            (url, h, _now()))
        self.conn.commit()

    # ---- health ----
    def update_health(self, publisher_id, publisher_name, ok,
                      item_count, error, note):
        now = _now()
        prev = self.conn.execute(
            "SELECT consecutive_empty FROM site_health WHERE publisher_id = ?",
            (publisher_id,)).fetchone()
        prev_empty = prev["consecutive_empty"] if prev else 0
        consecutive_empty = (prev_empty + 1) if (ok and item_count == 0) else (
            0 if ok else prev_empty)
        self.conn.execute(
            """INSERT INTO site_health
               (publisher_id, publisher_name, last_run, last_ok,
                last_item_count, consecutive_empty, last_error, note)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(publisher_id) DO UPDATE SET
                 publisher_name=excluded.publisher_name,
                 last_run=excluded.last_run,
                 last_ok=CASE WHEN excluded.last_ok IS NOT NULL
                              THEN excluded.last_ok ELSE site_health.last_ok END,
                 last_item_count=excluded.last_item_count,
                 consecutive_empty=excluded.consecutive_empty,
                 last_error=excluded.last_error,
                 note=excluded.note""",
            (publisher_id, publisher_name, now, now if ok else None,
             item_count, consecutive_empty, error, note))
        self.conn.commit()

    def health_rows(self):
        cur = self.conn.execute(
            "SELECT * FROM site_health ORDER BY publisher_name")
        return [dict(r) for r in cur.fetchall()]

    # ---- runs ----
    def record_run(self, started_at, sites_ok, sites_failed, new_count):
        self.conn.execute(
            """INSERT INTO runs(started_at, finished_at, sites_ok,
                                sites_failed, new_count)
               VALUES (?,?,?,?,?)""",
            (started_at, _now(), sites_ok, sites_failed, new_count))
        self.conn.commit()

    def last_run(self):
        row = self.conn.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
        return dict(row) if row else None
