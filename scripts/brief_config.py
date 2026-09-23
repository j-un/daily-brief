import json
from collections.abc import Mapping
from dataclasses import dataclass

KEYWORD_MAX_LEN = 64
STAR_CAP = 5

CATEGORIES: tuple[tuple[str, str], ...] = (
    ("tech", "🤖 Tech全般"),
    ("business", "💼 ビジネス / スタートアップ"),
    ("dev_tools", "🔧 開発・ツール"),
    ("music_culture", "🎵 音楽 / 機材 / カルチャー"),
    ("book_science", "📚 読書・サイエンス"),
    ("other", "🗂 その他"),
)
CATEGORY_KEYS = frozenset(key for key, _heading in CATEGORIES)

_INTEREST_KEYS = frozenset({"rubric", "exclude_keywords"})


class ConfigError(ValueError):
    pass


class Rubric:
    # Not a str because a keyword loop must not walk the curator text.
    __slots__ = ("text",)

    def __init__(self, text: str) -> None:
        if not isinstance(text, str):
            raise ConfigError("interests.rubric must be a str")
        stripped = text.strip()
        if not stripped:
            raise ConfigError("interests.rubric is blank")
        self.text = stripped


@dataclass(frozen=True)
class DomainCap:
    max_per_domain: int | None
    exempt: frozenset[str]


@dataclass(frozen=True)
class BriefConfig:
    rubric: Rubric
    exclude_keywords: tuple[str, ...]
    domain_cap: DomainCap


def parse_brief_config(raw) -> BriefConfig:
    if not isinstance(raw, Mapping):
        raise ConfigError("root must be a mapping")

    interests = raw.get("interests")
    if not isinstance(interests, Mapping):
        raise ConfigError("interests is missing or not a mapping")

    for key in interests:
        if key not in _INTEREST_KEYS:
            raise ConfigError(f"interests.{key} is not allowed")

    if "rubric" not in interests:
        raise ConfigError("interests.rubric is missing")
    rubric = Rubric(interests["rubric"])

    if "exclude_keywords" not in interests:
        exclude_keywords: tuple[str, ...] = ()
    else:
        exclude_keywords = _parse_exclude_keywords(interests["exclude_keywords"])
    domain_cap = _parse_domain_cap(raw.get("selection"))
    return BriefConfig(rubric, exclude_keywords, domain_cap)


def selection_prompt(rubric: Rubric, articles: list[dict]) -> str:
    category_lines = "\n".join(f"- {key}: {heading}" for key, heading in CATEGORIES)
    contract = (
        "## 出力契約\n"
        "形式はここの指定に従う。関心の文章は直前のブロックだけである。この契約は関心を足さない。\n"
        "渡される各記事にあるのは title と summary だけである。\n"
        "category は次のキーのいずれかである。コロンの右はブリーフに出る見出しである。\n"
        f"{category_lines}\n"
        "starred は真偽値である。true にするのは、直前の関心の文章で最も優先している記事だけである。"
        f"true は最大 {STAR_CAP} 件である。\n"
        "JSON だけを返す。説明文とコードブロックは付けない。id は記事リストの整数をそのまま使う。\n"
        '{"picked":[{"id":0,"category":"tech","starred":false}]}'
    )
    compact = json.dumps(articles, ensure_ascii=False, separators=(",", ":"))
    return (
        f"{rubric.text}\n"
        "\n"
        f"{contract}\n"
        "\n"
        f"## 記事リスト（{len(articles)}件）\n"
        "\n"
        f"{compact}"
    )


def clear_extra_stars(picked: list[dict]) -> list[dict]:
    kept = 0
    cleared: list[dict] = []
    for item in picked:
        copied = dict(item)
        if copied.get("starred") is True:
            if kept < STAR_CAP:
                kept += 1
            else:
                copied["starred"] = False
        cleared.append(copied)
    return cleared


def _parse_exclude_keywords(raw) -> tuple[str, ...]:
    if not isinstance(raw, list) or not all(isinstance(keyword, str) for keyword in raw):
        raise ConfigError("interests.exclude_keywords must be a list of str")
    stored: list[str] = []
    for keyword in raw:
        if "\n" in keyword or "\r" in keyword:
            raise ConfigError("interests.exclude_keywords contains a newline")
        stripped = keyword.strip()
        if not stripped:
            raise ConfigError("interests.exclude_keywords contains an empty keyword")
        if len(stripped) > KEYWORD_MAX_LEN:
            raise ConfigError(
                f"interests.exclude_keywords entry exceeds {KEYWORD_MAX_LEN} characters"
            )
        stored.append(stripped.lower())
    return tuple(stored)


def _parse_domain_cap(selection) -> DomainCap:
    if selection is None:
        return DomainCap(None, frozenset())
    if not isinstance(selection, Mapping):
        raise ConfigError("selection must be a mapping")

    if "max_per_domain" in selection:
        value = selection["max_per_domain"]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ConfigError(
                f"selection.max_per_domain must be an int >= 1, got {value!r}"
            )
        max_per_domain = value
    else:
        max_per_domain = None

    if "max_per_domain_exempt" not in selection:
        exempt = frozenset()
    else:
        exempt_raw = selection["max_per_domain_exempt"]
        if not isinstance(exempt_raw, list) or not all(
            isinstance(host, str) for host in exempt_raw
        ):
            raise ConfigError("selection.max_per_domain_exempt must be a list of str")
        hosts: list[str] = []
        for host in exempt_raw:
            normalized = host.strip().lower()
            if normalized.startswith("www."):
                normalized = normalized[4:]
            if normalized:
                hosts.append(normalized)
        exempt = frozenset(hosts)

    return DomainCap(max_per_domain, exempt)
