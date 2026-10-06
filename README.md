# shinchaku-watcher — 吹奏楽譜 新着監視システム

50社超の吹奏楽譜出版社の「新着楽譜」を**毎日自動で**集めて一元把握するための
システムです。サーバー維持費ゼロ（GitHub Actions の無料枠）で動きます。

## 設計の考え方：50本のスクレイパーを書かない

各社サイトは形式がバラバラですが、サイトごとに専用コードを書くと50本の
メンテ地獄になり、リニューアルのたびに壊れます。そこで取得手段を
**「頑丈な順」に階層化**し、大半を**共通エンジン＋設定ファイル1行**で吸収します。

| 層 | method | 内容 | 設定 |
|----|--------|------|------|
| 1 | `feed` | RSS/Atom をそのまま読む。最も頑丈 | フィードURL だけ |
| 2 | `listing` | 新着ページから「商品リンクの正規表現」で抽出 | ページURL＋正規表現1本 |
| 3 | `hash` | ページ主要部のハッシュ差分で「変化」を検知 | ページURL だけ |

サイトを増やすときに触るのは **`registry.yaml` だけ**。Pythonコードは変えません。

### 登録済み41社（「出版社.xlsx」より）
`registry.yaml` に41社を登録済みです。**28社は取得方式を確認して有効化**、
**13社は新着の取り込み口が未確認で保留中**（`enabled: false`）です。内訳と各社の
状態は、導入手順書の「付録」に一覧があります。確認できた主なパターン:
- Shopify系 → 新着コレクションの Atom フィード（例: ウィンズスコア、ROCKET MUSIC）
- Shop-Pro/カラーミー系 → `?mode=atom` でフィード取得（例: CAFUA、マエストロ、Golden Hearts）
- おちゃのこネット → `/rss/rss.php`（例: ゼーレ）
- WordPress系 → `/feed/`（例: ティーダ、FORNAX、Stone Music）
- 独自EC → 新着ページ + 商品リンクの正規表現（例: ミュージックエイト、ブレーン、フォスター、音楽之友社）

## 取得する情報（第1段階）

まずは **リンク＋タイトル＋検知日** を確実に取ります（＝「新しい何かが出た」を
取りこぼさない）。曲名・作曲/編曲・編成・難易度・価格といったフルメタデータは、
`Item` に項目が用意してあるので第2段階で各サイトに追加できます。

## 出力（`public/`）

- `index.html` … **作業用ダッシュボード**。`new_items.json` を読み込むクライアント型UIで、
  出版社フィルタ・検索・検知日絞り込み（今日/7日/すべて）、各行の「登録済み」で個別消去、
  「表示中をすべて登録済みに」で一括消去、「コピー」で曲名/URL/出版社をまとめて取得（カタログ登録用）、
  下部に折りたたみの稼働状況。「登録済み」状態は閲覧端末のブラウザ（localStorage）に保存されます。
- `digest.html` … **その日の新着だけの簡易ページ**（ダッシュボードの「今日」絞り込みでほぼ代用可）
- `new_items.json` … 機械可読データ（items＋稼働状況＋実行情報。比較検索サイト等の素材）

状態は `data/watcher.db`（SQLite）に保存。`first_seen`（初回検知日）で新着を判定します。
運用（日々の使い方・消し込み・出版社ごとの確認）は別紙「運用マニュアル」を参照してください。

## ローカルでの使い方

```bash
pip install -r requirements.txt

python -m watcher.run --list          # 設定サイトの一覧
python -m watcher.run                 # 全サイト実行 → public/ に出力
python -m watcher.run --only music8   # 1社だけ実行(動作確認・デバッグ用)
```

ロジックの検証（ネットワーク不要）:
```bash
python tests/offline_test.py
```

## GitHub Actions での常時運用

1. このフォルダをそのまま GitHub リポジトリに push。
2. `.github/workflows/watch.yml` が **毎日 07:00(JST)** に自動実行します
   （`Actions` タブの `Run workflow` で手動実行も可能）。
3. 実行ごとに `data/`（状態）と `public/`（出力）をリポジトリへコミットするので、
   新着の履歴が積み上がります。
4. ダッシュボードをWeb公開したい場合は `Settings > Pages` のソースを
   `public/` に設定（またはワークフロー末尾のコメント部分を有効化）。

> GitHub Actions のクラウド環境は毎回まっさらなので、状態（`data/watcher.db`）を
> リポジトリにコミットして引き継ぎます。50社・1日1回なら容量・実行時間とも
> 無料枠で十分収まります。

## サイトの増やし方（`registry.yaml`）

新しい出版社は、`sites:` にエントリを1つ足すだけです。

```yaml
# Shopify系(新着コレクション名はサイトで確認)
- id: foo
  name: ○○ミュージック
  method: feed
  url: https://foo.example/collections/new.atom

# 独自EC/一覧ページ
- id: bar
  name: △△出版
  method: listing
  url: https://bar.example/new/
  item_link_pattern: "/item/\\d+"     # 商品詳細URLの共通部分を正規表現で

# WordPress系(たいてい /feed/ がある)
- id: baz
  name: □□楽譜
  method: feed
  url: https://baz.example/feed/

# 頑固なサイト(変化だけ検知)
- id: qux
  name: ××社
  method: hash
  url: https://qux.example/whatsnew.html
  content_selector: "main"
```

### 新しいサイトの調べ方（目安）
1. 新着ページのHTMLソースを開き、`<head>` に `rss` / `atom` / `feed` の
   `<link>` があれば **層1(feed)**。Shopify は `…/collections/<名前>.atom`。
   WordPress は `…/feed/`。
2. 無ければ新着ページで商品詳細リンクを1つ右クリック→URLをコピーし、
   数字やIDの共通部分を正規表現にして **層2(listing)** の `item_link_pattern` に。
3. どちらも難しいサイトだけ **層3(hash)** で「変化検知」にしておき、
   後で手を入れます。

## 壊れ検知（50社でも破綻させないために）

各サイトの取得結果は `site_health` に記録され、ダッシュボードに表示されます。

- **エラー**（赤）… 取得自体が失敗（HTTPエラー等）
- **要確認**（黄）… 取得は成功したのに**新着が2回連続で0件**
  → サイトのレイアウト変更で `item_link_pattern` が合わなくなった可能性。
  その行だけ設定を直せばよく、他の49社は動き続けます。

## 礼儀とコスト

- `robots.txt` を尊重。ホスト単位のアクセス間隔（既定3秒）とリトライを実装。
- 条件付きGET（ETag / Last-Modified）で無駄な転送を避けます。
- 外部AI APIは一切使いません（変動コストなし）。どうしても構造が取れない
  数社だけ、将来 `--use-ai` 的な初期設定支援を足す余地を残しています。

## ファイル構成

```
shinchaku-watcher/
  registry.yaml              監視対象(ここだけ編集すればサイトを増やせる)
  requirements.txt
  watcher/
    run.py        オーケストレータ(CLI)
    fetch.py      礼儀正しいHTTP取得(robots・キャッシュ・リトライ)
    sources.py    階層型アダプタ(feed/listing/hash)
    store.py      SQLite(状態・履歴・稼働状況)
    normalize.py  URL/タイトル正規化・重複排除キー
    report.py     ダッシュボード/ダイジェスト/JSON 生成
  tests/
    offline_test.py  ネットワーク非依存のロジック検証
  .github/workflows/
    watch.yml     毎日の自動実行
```

## 次の段階（メモ）

- 保留中13社の新着ページURL／リンクパターンを特定して有効化（導入手順書「付録」参照）
- フルメタデータ抽出（曲名・作曲/編曲・編成・難易度・価格・品番）
- `new_items.json` を比較検索サイト（フェーズ3）のデータ源として接続
- 新着ダイジェストのメール/通知配信（任意）
