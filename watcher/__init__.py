"""
shinchaku-watcher — 吹奏楽譜出版社の新着楽譜を常時監視する共通エンジン。

設計方針:
- サイトごとに専用コードを書かない。取得手段を「頑丈な順」に階層化し、
  共通エンジン + 設定ファイル(registry.yaml)で50社超を吸収する。
    1. feed    : RSS/Atom (最も頑丈。Shopify等)
    2. listing : 新着ページを「商品リンクの正規表現」で抽出 (設定1行)
    3. hash    : ページ主要部のハッシュ差分 (頑固なサイトのフォールバック)
- 変動コストはゼロ: 外部AI APIを使わず requests + BeautifulSoup のみ。
- 状態は SQLite に持ち、初回検知日(first_seen)で「新着」を判定する。
"""

__version__ = "0.1.0"
