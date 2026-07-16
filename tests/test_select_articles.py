"""scripts/select_articles.py の domain_of / apply_domain_cap の unit test。

scripts/ はパッケージではないため importlib.util.spec_from_file_location で
select_articles.py を直接ロードする。
"""

import importlib.util
from pathlib import Path

_SPEC_PATH = Path(__file__).parent.parent / "scripts" / "select_articles.py"
_spec = importlib.util.spec_from_file_location("select_articles", _SPEC_PATH)
assert _spec is not None and _spec.loader is not None
select_articles = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(select_articles)

domain_of = select_articles.domain_of
apply_domain_cap = select_articles.apply_domain_cap


class TestDomainOf:
    def test_normal_url(self):
        assert domain_of("https://example.com/path/to/article") == "example.com"

    def test_strips_leading_www(self):
        assert domain_of("https://www.example.com/article") == "example.com"

    def test_lowercases_host(self):
        assert domain_of("https://EXAMPLE.COM/article") == "example.com"

    def test_empty_string_returns_empty(self):
        assert domain_of("") == ""

    def test_malformed_url_returns_empty(self):
        assert domain_of("not a url") == ""


class TestApplyDomainCap:
    def test_max_per_domain_none_passes_through_all(self):
        candidates = [
            {"link": "https://a.com/1"},
            {"link": "https://a.com/2"},
            {"link": "https://b.com/1"},
        ]
        kept, dropped = apply_domain_cap(candidates, None)
        assert kept == candidates
        assert dropped == {}

    def test_excess_over_cap_is_dropped_and_counted(self):
        candidates = [
            {"link": "https://a.com/1"},
            {"link": "https://a.com/2"},
            {"link": "https://a.com/3"},
            {"link": "https://b.com/1"},
        ]
        kept, dropped = apply_domain_cap(candidates, max_per_domain=2)
        assert kept == [
            {"link": "https://a.com/1"},
            {"link": "https://a.com/2"},
            {"link": "https://b.com/1"},
        ]
        assert dropped == {"a.com": 1}

    def test_preserves_input_order(self):
        candidates = [
            {"link": "https://a.com/1"},
            {"link": "https://b.com/1"},
            {"link": "https://a.com/2"},
            {"link": "https://b.com/2"},
        ]
        kept, _ = apply_domain_cap(candidates, max_per_domain=1)
        assert kept == [
            {"link": "https://a.com/1"},
            {"link": "https://b.com/1"},
        ]

    def test_link_without_domain_is_always_kept(self):
        candidates = [
            {"link": "not a url"},
            {"link": "https://a.com/1"},
            {"link": "https://a.com/2"},
            {"link": "not a url either"},
        ]
        kept, dropped = apply_domain_cap(candidates, max_per_domain=1)
        assert kept == [
            {"link": "not a url"},
            {"link": "https://a.com/1"},
            {"link": "not a url either"},
        ]
        assert dropped == {"a.com": 1}

    def test_exempt_domain_keeps_all_over_cap(self):
        candidates = [
            {"link": "https://a.com/1"},
            {"link": "https://a.com/2"},
            {"link": "https://a.com/3"},
        ]
        kept, dropped = apply_domain_cap(
            candidates, max_per_domain=1, exempt_domains=frozenset({"a.com"})
        )
        assert kept == candidates
        assert dropped == {}

    def test_exempt_domain_does_not_affect_cap_on_other_domains(self):
        candidates = [
            {"link": "https://a.com/1"},
            {"link": "https://a.com/2"},
            {"link": "https://b.com/1"},
            {"link": "https://b.com/2"},
        ]
        kept, dropped = apply_domain_cap(
            candidates, max_per_domain=1, exempt_domains=frozenset({"a.com"})
        )
        assert kept == [
            {"link": "https://a.com/1"},
            {"link": "https://a.com/2"},
            {"link": "https://b.com/1"},
        ]
        assert dropped == {"b.com": 1}

    def test_exempt_list_requires_exact_normalized_host_match(self):
        candidates = [
            {"link": "https://blog.example.com/1"},
            {"link": "https://example.com/1"},
            {"link": "https://example.com/2"},
        ]
        kept, dropped = apply_domain_cap(
            candidates,
            max_per_domain=1,
            exempt_domains=frozenset({"blog.example.com"}),
        )
        assert kept == [
            {"link": "https://blog.example.com/1"},
            {"link": "https://example.com/1"},
        ]
        assert dropped == {"example.com": 1}
