"""scripts/summarize_articles.py の要約JSON解釈。

途中で切れたモデル出力から、完結した要約だけを採用できることを確認する。
"""

import importlib.util
import json
from pathlib import Path

import pytest

_SPEC_PATH = Path(__file__).parent.parent / "scripts" / "summarize_articles.py"
_spec = importlib.util.spec_from_file_location("summarize_articles", _SPEC_PATH)
assert _spec is not None and _spec.loader is not None
summarize_articles = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(summarize_articles)

parse_summaries = summarize_articles.parse_summaries
usable_summary = summarize_articles.usable_summary


def test_complete_json_returns_every_summary():
    text = json.dumps(
        {
            "summaries": [
                {"id": 0, "summary_jp": "完結した要約。"},
                {"id": 1, "summary_jp": "もう一件。"},
            ]
        },
        ensure_ascii=False,
    )
    assert parse_summaries(text) == [
        {"id": 0, "summary_jp": "完結した要約。"},
        {"id": 1, "summary_jp": "もう一件。"},
    ]


def test_truncated_json_keeps_closed_objects_only(capsys):
    text = (
        '{"summaries":['
        '{"id":0,"summary_jp":"Cloudflareがリクエストを追跡する仕組み。"},'
        '{"id":1,"summary_jp":"天文データ解析の体験談。"},'
        '{"id":2,"summary_jp":"CloudflareがCo'
    )
    with pytest.raises(json.JSONDecodeError):
        summarize_articles.extract_json(text)

    got = parse_summaries(text)
    assert [item["id"] for item in got] == [0, 1]
    assert "完結した 2 件" in capsys.readouterr().err


def test_truncated_after_last_brace_still_parses_closed_objects():
    # 最後の } で切ると配列が閉じず、Expecting ',' delimiter になる。
    text = (
        '{"summaries":[{"id":0,"summary_jp":"一件目。"},'
        '{"id":1,"summary_jp":"二件目。"}'
    )
    got = parse_summaries(text)
    assert [item["summary_jp"] for item in got] == ["一件目。", "二件目。"]


def test_unclosed_json_with_no_complete_object_still_raises():
    with pytest.raises(json.JSONDecodeError):
        parse_summaries('{"summaries":[{"id":0,"summary_jp":"途中')


def test_usable_summary_rejects_blank_and_replacement_character():
    assert usable_summary("パイプラインの監視。") == "パイプラインの監視。"
    assert usable_summary("   ") is None
    assert usable_summary("品質監視を、\ufffd\ufffd\ufffdイプライン稼働") is None
    assert usable_summary(None) is None
