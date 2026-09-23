"""scripts/brief_config.py の parse / prompt / star cap。

scripts/ はパッケージではないため importlib で直接ロードする。
"""

import importlib.util
from pathlib import Path

import pytest

_SPEC_PATH = Path(__file__).parent.parent / "scripts" / "brief_config.py"
_spec = importlib.util.spec_from_file_location("brief_config", _SPEC_PATH)
assert _spec is not None and _spec.loader is not None
brief_config = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(brief_config)

parse_brief_config = brief_config.parse_brief_config
selection_prompt = brief_config.selection_prompt
clear_extra_stars = brief_config.clear_extra_stars
ConfigError = brief_config.ConfigError
Rubric = brief_config.Rubric


def test_selection_prompt_is_rubric_contract_and_compact_json():
    rubric = Rubric("読み手は実務のエンジニアです。")
    articles = [{"id": 0, "title": "Aurora timeout", "summary": "接続が切れる"}]
    expected = """読み手は実務のエンジニアです。

## 出力契約
形式はここの指定に従う。関心の文章は直前のブロックだけである。この契約は関心を足さない。
渡される各記事にあるのは title と summary だけである。
category は次のキーのいずれかである。コロンの右はブリーフに出る見出しである。
- tech: 🤖 Tech全般
- business: 💼 ビジネス / スタートアップ
- dev_tools: 🔧 開発・ツール
- music_culture: 🎵 音楽 / 機材 / カルチャー
- book_science: 📚 読書・サイエンス
- other: 🗂 その他
starred は真偽値である。true にするのは、直前の関心の文章で最も優先している記事だけである。true は最大 5 件である。
JSON だけを返す。説明文とコードブロックは付けない。id は記事リストの整数をそのまま使う。
{"picked":[{"id":0,"category":"tech","starred":false}]}

## 記事リスト（1件）

[{"id":0,"title":"Aurora timeout","summary":"接続が切れる"}]"""
    assert selection_prompt(rubric, articles) == expected


def test_parse_brief_config_minimal_document():
    raw = {
        "feeds": [{"name": "ignored"}],
        "interests": {
            "rubric": "  読み手は実務のエンジニアです。\n",
            "exclude_keywords": ["広告", "PR記事"],
        },
        "selection": {
            "max_per_domain": 3,
            "max_per_domain_exempt": ["WWW.Speakerdeck.com"],
        },
    }
    config = parse_brief_config(raw)
    assert config.rubric.text == "読み手は実務のエンジニアです。"
    assert config.exclude_keywords == ("広告", "pr記事")
    assert config.domain_cap.max_per_domain == 3
    assert config.domain_cap.exempt == frozenset({"speakerdeck.com"})


def test_themes_key_raises():
    with pytest.raises(ConfigError, match="themes"):
        parse_brief_config(
            {"interests": {"rubric": "本文です。", "themes": ["SRE"]}}
        )


def test_keyword_longer_than_64_raises():
    with pytest.raises(ConfigError, match="exclude_keywords"):
        parse_brief_config(
            {
                "interests": {
                    "rubric": "本文です。",
                    "exclude_keywords": ["a" * 65],
                }
            }
        )


def test_max_per_domain_bool_raises():
    with pytest.raises(ConfigError, match="max_per_domain"):
        parse_brief_config(
            {
                "interests": {"rubric": "本文です。"},
                "selection": {"max_per_domain": True},
            }
        )


def test_clear_extra_stars_keeps_all_and_only_first_five():
    picked = [{"id": i, "starred": True} for i in range(6)]
    picked.append({"id": 6, "starred": False})
    result = clear_extra_stars(picked)
    assert result == [
        {"id": 0, "starred": True},
        {"id": 1, "starred": True},
        {"id": 2, "starred": True},
        {"id": 3, "starred": True},
        {"id": 4, "starred": True},
        {"id": 5, "starred": False},
        {"id": 6, "starred": False},
    ]
    assert clear_extra_stars(result) == result
    assert picked[5]["starred"] is True
