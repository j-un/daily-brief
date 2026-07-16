# Daily Brief

## 概要

RSSフィードから収集した記事をキュレーションし、日次 Markdown ブリーフィングを生成する。
フィード取得・記事選定・要約生成・Markdown 描画はそれぞれ独立したスクリプトが担当する。

---

## 設定ファイル

フィードリスト・関心テーマ・除外キーワードは `config.yaml` で管理する。
フィードの追加・削除やキーワード変更を求められた場合は `config.yaml` を更新すること。

> **参照**: `config.yaml` — feeds / interests / selection セクション

---

## ワークフロー

```
fetch_feeds.py → pool.json
prepare_brief.py → articles.json
select_articles.py (Sonnet) → selected.json   # 関連度判定・カテゴリ分類・⭐選定
summarize_articles.py (Haiku) → summaries.json # 日本語要約生成
render_brief.py → docs/brief-YYYY-MM-DD.md    # Markdown 描画（Claude 不使用）
```

選定・要約のプロンプトとルールは各スクリプト内に記述されている。

---

## カテゴリ enum

記事の分類カテゴリは以下の固定リストを使用する（`select_articles.py` と `render_brief.py` で共有）。

| enum 値 | 見出し |
|---|---|
| `tech_ai` | 🤖 Tech / AI |
| `business` | 💼 ビジネス / スタートアップ |
| `dev_tools` | 🔧 開発・ツール |
| `music_culture` | 🎵 音楽 / 機材 / カルチャー |
| `book_science` | 📚 読書・サイエンス |
| `other` | 🗂 その他 |

新カテゴリを追加する場合は `select_articles.py:CATEGORY_ENUM` と `render_brief.py:CATEGORY_ORDER/CATEGORY_LABELS` を更新すること。
