---
name: rss-digest
description: >
  毎日の情報収集を支援するRSSダイジェスト生成スキル。
  登録済みRSSフィードから新着記事を取得し、ユーザーの関心に合った記事をピックアップ・要約して
  Markdownレポートとして出力する。
  「今日のニュース」「最新情報まとめ」「RSSチェック」「情報収集」「フィード確認」
  「ダイジェスト作って」「ニュースまとめて」などの発話で必ずこのスキルを使うこと。
  日々のキャッチアップ、トレンド把握、技術ニュースの確認など情報収集全般に対応する。
---

# RSS Digest スキル

## 概要

登録済みRSSフィードから新着記事を取得し、ハイブリッドフィルタリング（キーワード粗選別 → Claude精査）で
ユーザーの関心に合った記事をピックアップし、Markdownのデイリーダイジェストを生成する。

---

## 設定ファイル

フィードリスト・キーワード・関心テーマは `config.yaml` で管理する。
ユーザーがフィードの追加・削除やキーワード変更を求めた場合は `config.yaml` を更新すること。

> **参照**: `<skill_dir>/config.yaml` — feeds / interests セクション

---

## ワークフロー

### Step 1: フィード取得と差分抽出

`scripts/fetch_feeds.py` を実行して新着記事を取得する。
スクリプトはPEP 723のインラインメタデータで依存を宣言しているため、
`uv run` で実行すれば feedparser のインストールは自動で行われる。

```bash
uv run <skill_dir>/scripts/fetch_feeds.py \
  --config <skill_dir>/config.yaml \
  --state-file ~/.rss-digests/state.json \
  --hours 24
```

引数の説明:
- `--config`: `config.yaml` のパス（feeds セクションからフィード一覧を読み込む）
- `--state-file`: 前回取得状態を保存するJSONファイル（初回は自動作成される）
- `--hours`: 何時間前まで遡るか（デフォルト24。「今週分」なら168を指定）

スクリプトはJSON形式で新着記事リストを標準出力に返す。各記事は `title`, `link`, `summary`, `published`, `feed_name`, `category`, `entry_id` を持つ。

### Step 2: キーワードによる粗フィルタリング

Step 1 の出力JSONを `scripts/filter_articles.py` にパイプで渡す。

```bash
echo '<Step1の出力>' | uv run <skill_dir>/scripts/filter_articles.py \
  --config <skill_dir>/config.yaml
```

`config.yaml` の `interests.keywords` / `interests.exclude_keywords` を使い、
タイトルまたは概要にキーワードが含まれる記事だけを通過させ、除外キーワードに一致する記事は除去する。
結果はJSON形式で標準出力に返る。各記事に `matched_keywords` フィールドが追加される。

**キーワードが一つもマッチしない場合**: 全記事の上位20件をそのまま Step 3 へ渡す（幅広くカバーするため）。

### Step 3: Claude による精査と要約

Step 2 を通過した記事リストを受け取り、以下を行う。これはスクリプトではなく Claude 自身が行う作業である。

1. **関連度判定**: 上記「themes」に照らして、本当にユーザーの関心に合うか判定する。
   **title と summary のみで判断し、web_fetch は使用しないこと**（トークン節約のため）。
   関連度が低いものは除外する。
2. **要約生成**: 残った記事ごとに日本語で1〜2文の要約を作成する。
3. **カテゴリ分類**: 記事をカテゴリ別にグルーピングする（RSSのカテゴリを参考にしつつ、内容に応じて再分類してよい）。
4. **重要度ランク**: 特に注目すべき記事（トレンドの転換点、大型発表、影響の大きいニュースなど）には ⭐ を付ける。

### Step 4: Markdownレポート生成

`<skill_dir>/templates/daily.md` のテンプレートに従ってMarkdownファイルを生成する。

- **出力先**: `~/rss-digests/digest-YYYY-MM-DD.md`（ディレクトリは `mkdir -p` で作成）
- 同日に複数回実行した場合は上書きする
- カテゴリは固定ではなく、記事の内容に応じて柔軟に作成・統合してよい
- 記事が0件のカテゴリは省略する

---

## 状態管理

`~/.rss-digests/state.json` に以下を保存する：

```json
{
  "last_run": "2026-03-28T09:00:00+09:00",
  "seen_ids": {
    "https://hnrss.org/best": ["entry-id-1", "entry-id-2"]
  }
}
```

- `last_run`: 前回実行日時。次回は `last_run` 以降の記事だけ取得する
- `seen_ids`: フィードごとの既読エントリID。直近500件を保持し、古いものは自動削除する

状態ファイルが存在しない場合（初回実行）は `--hours` 分だけ遡る。

---

## エラーハンドリング

- 個別フィードの取得失敗: エラーをログに出しつつ他のフィードの処理を続行する
- 全フィードが失敗: ネットワーク設定の確認を促すメッセージを出す
- 新着記事が0件: 「新着記事はありませんでした」と報告する
- `uv` 未インストール: `curl -LsSf https://astral.sh/uv/install.sh | sh` でインストールを促す

---

## 注意事項

- このスキルはネットワークアクセスが必要。ネットワークが無効な環境では、その旨をユーザーに伝えること
- 記事本文の全文取得は行わない（RSSのtitle・description・linkのみ使用）。web_fetch はトークンコストが高いため使用禁止
- レポートは日本語で生成する
