"""
run.py - オーケストレータ(CLIエントリポイント)。

registry.yaml を読み、有効な各サイトを順に取得 → SQLiteに保存 → 稼働状況を更新
→ ダッシュボード/ダイジェスト/JSON を出力する。

1サイトの失敗や例外が全体を止めないよう、各サイトは try で隔離する。

使い方:
    python -m watcher.run --config registry.yaml --out public
    python -m watcher.run --only winds-score          # 1社だけ
    python -m watcher.run --list                        # 設定の一覧表示
"""
import argparse
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .fetch import Fetcher
from .sources import collect
from .store import Store
from . import report


def load_config(path):
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg.setdefault("defaults", {})
    cfg.setdefault("sites", [])
    return cfg


def _merge_defaults(site, defaults):
    merged = dict(defaults)
    merged.update(site)
    return merged


def main(argv=None):
    ap = argparse.ArgumentParser(description="吹奏楽譜 新着監視")
    ap.add_argument("--config", default="registry.yaml")
    ap.add_argument("--data", default="data", help="DB・キャッシュの保存先")
    ap.add_argument("--out", default="public", help="HTML/JSON出力先")
    ap.add_argument("--only", help="指定IDのサイトだけ実行")
    ap.add_argument("--list", action="store_true", help="設定を一覧表示して終了")
    ap.add_argument("--no-robots", action="store_true",
                    help="robots.txtを無視(非推奨・検証用)")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    defaults = cfg["defaults"]
    sites = [_merge_defaults(s, defaults) for s in cfg["sites"]]

    if args.list:
        for s in sites:
            flag = "on " if s.get("enabled", True) else "off"
            print(f"[{flag}] {s['id']:20} {s.get('method','listing'):8} "
                  f"{s.get('name','')}  {s.get('url','')}")
        return 0

    if args.only:
        sites = [s for s in sites if s["id"] == args.only]
        if not sites:
            print(f"[エラー] id '{args.only}' が設定に見つかりません", file=sys.stderr)
            return 1

    data_dir = Path(args.data)
    out_dir = Path(args.out)
    data_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    store = Store(data_dir / "watcher.db")
    fetcher = Fetcher(
        cache_dir=data_dir / "cache",
        user_agent=defaults.get("user_agent") or
                   "shinchaku-watcher/0.1 (+band new-arrivals monitor)",
        obey_robots=not args.no_robots and defaults.get("obey_robots", True),
        default_rate_limit=defaults.get("rate_limit_sec", 2.0),
    )

    started = datetime.now(timezone.utc).astimezone().isoformat()
    sites_ok = sites_failed = new_total = 0

    for s in sites:
        if not s.get("enabled", True):
            continue
        name = s.get("name", s["id"])
        try:
            res = collect(s, fetcher, store)
        except Exception as e:  # サイト固有の予期せぬ例外を隔離
            traceback.print_exc()
            store.update_health(s["id"], name, ok=False, item_count=0,
                                error=f"例外: {e}", note="")
            sites_failed += 1
            print(f"  ✗ {name}: 例外 {e}")
            continue

        if not res.ok:
            store.update_health(s["id"], name, ok=False, item_count=0,
                                error=res.error, note=res.note)
            sites_failed += 1
            print(f"  ✗ {name}: {res.error}")
            continue

        new_items = store.upsert_items(res.items)
        store.update_health(s["id"], name, ok=True, item_count=len(res.items),
                            error=None, note=res.note)
        sites_ok += 1
        new_total += len(new_items)
        tag = f" (新着 {len(new_items)})" if new_items else ""
        warn = f"  ⚠ {res.note}" if res.note else ""
        print(f"  ✓ {name}: 取得 {len(res.items)}{tag}{warn}")

    store.record_run(started, sites_ok, sites_failed, new_total)

    # 出力
    report.write_json(store, out_dir / "new_items.json")
    report.render_dashboard(store, out_dir / "index.html")
    digest_n = report.render_digest(store, out_dir / "digest.html")

    print(f"\n完了: 正常 {sites_ok} / 失敗 {sites_failed} / "
          f"本日新着 {digest_n} / 累計 {store.total_items()}")
    print(f"出力: {out_dir}/index.html, digest.html, new_items.json")
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
