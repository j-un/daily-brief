"""scripts/llm_cli.py の unit test。

実 CLI は呼ばず、run にフェイクを注入する。
scripts/ はパッケージではないため importlib.util.spec_from_file_location で
llm_cli.py を直接ロードする。
"""

import importlib.util
import json
from pathlib import Path

import pytest

_SPEC_PATH = Path(__file__).parent.parent / "scripts" / "llm_cli.py"
_spec = importlib.util.spec_from_file_location("llm_cli", _SPEC_PATH)
assert _spec is not None and _spec.loader is not None
llm_cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(llm_cli)

call_llm = llm_cli.call_llm
normalize_usage = llm_cli.normalize_usage
usage_has_data = llm_cli.usage_has_data
format_usage_line = llm_cli.format_usage_line
format_usage_report = llm_cli.format_usage_report
format_usage_files_report = llm_cli.format_usage_files_report
format_usage_footer = llm_cli.format_usage_footer
usage_label = llm_cli.usage_label


class FakeProcess:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class FakeRun:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self._result = FakeProcess(returncode, stdout, stderr)
        self.cmd = None

    def __call__(self, cmd, **kwargs):
        self.cmd = cmd
        return self._result


class TestCallLlm:
    def test_claude_json_returns_result_usage_cost(self):
        payload = {
            "result": "picked articles",
            "usage": {"input_tokens": 10, "output_tokens": 4},
            "total_cost_usd": 0.0123,
            "is_error": False,
        }
        fake = FakeRun(stdout=json.dumps(payload))
        text, usage, cost = call_llm(
            "prompt", role="select", provider="claude", run=fake
        )
        assert text == "picked articles"
        assert usage == {
            "input_tokens": 10,
            "output_tokens": 4,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        }
        assert cost == 0.0123

    def test_cursor_json_normalizes_camelcase_usage(self):
        payload = {
            "result": "picked",
            "usage": {
                "inputTokens": 8811,
                "outputTokens": 53,
                "cacheReadTokens": 5440,
                "cacheWriteTokens": 0,
            },
            "is_error": False,
        }
        fake = FakeRun(stdout=json.dumps(payload))
        text, usage, cost = call_llm(
            "prompt", role="select", provider="cursor", run=fake
        )
        assert text == "picked"
        assert usage == {
            "input_tokens": 8811,
            "output_tokens": 53,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 5440,
        }
        assert cost is None

    def test_cursor_json_without_usage_or_cost(self):
        payload = {"result": "summaries here", "is_error": False}
        fake = FakeRun(stdout=json.dumps(payload))
        text, usage, cost = call_llm(
            "prompt", role="summarize", provider="cursor", run=fake
        )
        assert text == "summaries here"
        assert usage == {}
        assert cost is None

    def test_is_error_true_raises(self):
        payload = {"result": "boom", "is_error": True}
        fake = FakeRun(stdout=json.dumps(payload))
        with pytest.raises(RuntimeError, match="boom"):
            call_llm("prompt", role="select", provider="claude", run=fake)

    def test_nonzero_returncode_raises(self):
        fake = FakeRun(returncode=2, stderr="fail")
        with pytest.raises(RuntimeError, match="exited with 2"):
            call_llm("prompt", role="select", provider="claude", run=fake)

    def test_env_cursor_builds_agent_argv_for_select(self, monkeypatch):
        monkeypatch.setenv("DAILY_BRIEF_LLM", "cursor")
        monkeypatch.delenv("DAILY_BRIEF_SELECT_MODEL", raising=False)
        fake = FakeRun(stdout=json.dumps({"result": "ok", "is_error": False}))
        call_llm("prompt", role="select", provider=None, run=fake)
        argv = fake.cmd
        assert argv[0] == "agent"
        assert "-p" in argv or "--print" in argv
        assert "--mode" in argv
        assert "ask" in argv
        assert "--output-format" in argv
        assert "json" in argv
        assert "--force" not in argv
        assert argv[argv.index("--model") + 1] == "cursor-grok-4.6-high"

    def test_cursor_summarize_uses_composer_model(self, monkeypatch):
        monkeypatch.delenv("DAILY_BRIEF_SUMMARIZE_MODEL", raising=False)
        fake = FakeRun(stdout=json.dumps({"result": "ok", "is_error": False}))
        call_llm("prompt", role="summarize", provider="cursor", run=fake)
        argv = fake.cmd
        assert argv[argv.index("--model") + 1] == "composer-2.5"

    def test_invalid_env_provider_raises(self, monkeypatch):
        monkeypatch.setenv("DAILY_BRIEF_LLM", "bogus")
        with pytest.raises(ValueError):
            call_llm("prompt", role="select", provider=None, run=FakeRun())

    def test_invalid_role_raises(self):
        with pytest.raises(ValueError):
            call_llm("prompt", role="nope", provider="claude", run=FakeRun())


class TestNormalizeUsage:
    def test_cursor_camelcase(self):
        raw = {
            "inputTokens": 100,
            "outputTokens": 20,
            "cacheReadTokens": 50,
            "cacheWriteTokens": 10,
        }
        assert normalize_usage(raw) == {
            "input_tokens": 100,
            "output_tokens": 20,
            "cache_creation_input_tokens": 10,
            "cache_read_input_tokens": 50,
        }

    def test_claude_snake_case(self):
        raw = {
            "input_tokens": 10,
            "cache_creation_input_tokens": 9447,
            "cache_read_input_tokens": 12212,
            "output_tokens": 45,
        }
        assert normalize_usage(raw) == raw

    def test_empty_returns_empty(self):
        assert normalize_usage({}) == {}
        assert normalize_usage(None) == {}

    def test_claude_keys_take_priority_over_cursor(self):
        raw = {
            "input_tokens": 1,
            "inputTokens": 99,
        }
        assert normalize_usage(raw)["input_tokens"] == 1


class TestFormatUsage:
    def test_empty_usage_shows_not_available(self):
        assert "not available" in format_usage_line("Selection", {}, None)
        assert "not available" in format_usage_report("Selection", {}, None)

    def test_cost_none_omits_cost_line(self):
        usage = {
            "input_tokens": 10,
            "output_tokens": 5,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        }
        report = format_usage_report("Selection", usage, None)
        assert "cost=" not in report
        assert "$0.0000" not in report

    def test_footer_without_cost(self):
        footer = format_usage_footer(0.0, False)
        assert "not available" in footer
        assert "$0.0000" not in footer

    def test_footer_with_cost(self):
        footer = format_usage_footer(0.0213, True)
        assert footer.endswith("total cost: $0.0213")

    def test_usage_has_data_false_for_empty(self):
        assert not usage_has_data({})
        assert usage_has_data(
            {
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            }
        )

    def test_cursor_omits_cache_creation(self):
        usage = {
            "input_tokens": 100,
            "output_tokens": 20,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 50,
        }
        line = format_usage_line("Selection", usage, None, provider="cursor")
        report = format_usage_report("Selection", usage, None, "cursor")
        assert "cache_creation" not in line
        assert "cache_creation" not in report
        assert "cache_read=50" in line
        assert "cache_read=50" in report

    def test_claude_includes_cache_creation(self):
        usage = {
            "input_tokens": 100,
            "output_tokens": 20,
            "cache_creation_input_tokens": 10,
            "cache_read_input_tokens": 50,
        }
        for provider in ("claude", None):
            line = format_usage_line("Selection", usage, None, provider)
            report = format_usage_report("Selection", usage, None, provider)
            assert "cache_creation=10" in line
            assert "cache_creation=10" in report
            assert "cache_read=50" in line
            assert "cache_read=50" in report

    def test_default_includes_cache_creation(self):
        usage = {
            "input_tokens": 10,
            "output_tokens": 5,
            "cache_creation_input_tokens": 3,
            "cache_read_input_tokens": 0,
        }
        line = format_usage_line("Selection", usage, None)
        report = format_usage_report("Selection", usage, None)
        assert "cache_creation=3" in line
        assert "cache_creation=3" in report

    def test_files_report_respects_provider_in_json(self, tmp_path):
        usage = {
            "input_tokens": 100,
            "output_tokens": 20,
            "cache_creation_input_tokens": 10,
            "cache_read_input_tokens": 50,
        }
        cursor_path = tmp_path / "cursor.json"
        claude_path = tmp_path / "claude.json"
        cursor_path.write_text(
            json.dumps(
                {
                    "label": "Selection",
                    "provider": "cursor",
                    "cost_usd": None,
                    "usage": usage,
                }
            ),
            encoding="utf-8",
        )
        claude_path.write_text(
            json.dumps(
                {
                    "label": "Summarize",
                    "provider": "claude",
                    "cost_usd": 0.01,
                    "usage": usage,
                }
            ),
            encoding="utf-8",
        )
        cursor_report = format_usage_files_report([str(cursor_path)])
        claude_report = format_usage_files_report([str(claude_path)])
        assert "cache_creation" not in cursor_report
        assert "cache_read=50" in cursor_report
        assert "cache_creation=10" in claude_report
        assert "cache_read=50" in claude_report


class TestUsageLabel:
    def test_select_returns_selection(self):
        assert usage_label("select") == "Selection"

    def test_summarize_with_suffix(self):
        assert usage_label("summarize", suffix="(retry)") == "Summarize (retry)"

    def test_invalid_role_raises(self):
        with pytest.raises(ValueError, match="role must be"):
            usage_label("invalid")
