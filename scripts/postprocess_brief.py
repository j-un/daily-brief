#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# ///
"""
ダイジェストMarkdownの後処理スクリプト

Markdownリンク [text](url) 内の | を \\| にエスケープする。
Jekyll が | をテーブル構文と誤認してリンクが壊れる問題への対策。
"""

import re
import sys


def escape_pipes_in_links(markdown: str) -> str:
    """Markdownリンクのテキスト部分にある | を \\| にエスケープする"""
    def replace_link(m: re.Match) -> str:
        text = re.sub(r"(?<!\\)\|", r"\\|", m.group(1))
        url = m.group(2)
        return f"[{text}]({url})"

    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", replace_link, markdown)


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <markdown-file>", file=sys.stderr)
        sys.exit(1)

    path = sys.argv[1]
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    result = escape_pipes_in_links(content)

    with open(path, "w", encoding="utf-8") as f:
        f.write(result)


if __name__ == "__main__":
    main()
