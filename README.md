# Daily Brief

- RSSフィードからデイリーブリーフィングを生成しGitHub Pagesで公開する
- 詳細は [CLAUDE.md](./CLAUDE.md) を参照

## ローカル実行

```bash
./scripts/daily-brief.sh --local-dry-run
./scripts/daily-brief.sh --local-dry-run --llm cursor
```

`--llm claude|cursor` または環境変数 `DAILY_BRIEF_LLM` で選定・要約の LLM CLI を切り替えられる。
