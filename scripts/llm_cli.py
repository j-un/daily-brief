#!/usr/bin/env python3
"""Claude Code CLI (`claude`) と Cursor CLI (`agent`) への LLM 呼び出し。"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable

_VALID_ROLES = ("select", "summarize")
_VALID_PROVIDERS = ("claude", "cursor")

_DEFAULT_MODELS = {
    ("select", "claude"): "claude-sonnet-5",
    ("summarize", "claude"): "claude-haiku-4-5-20251001",
    ("select", "cursor"): "cursor-grok-4.6-high",
    ("summarize", "cursor"): "composer-2.5",
}

_MODEL_ENV = {
    "select": "DAILY_BRIEF_SELECT_MODEL",
    "summarize": "DAILY_BRIEF_SUMMARIZE_MODEL",
}

USAGE_LABELS = {
    "select": "Selection",
    "summarize": "Summarize",
}


def usage_label(role: str, *, suffix: str = "") -> str:
    if role not in _VALID_ROLES:
        raise ValueError(f"role must be 'select' or 'summarize', got {role!r}")
    label = USAGE_LABELS[role]
    if suffix:
        return f"{label} {suffix}"
    return label

_CURSOR_USAGE_KEYS = {
    "inputTokens": "input_tokens",
    "outputTokens": "output_tokens",
    "cacheReadTokens": "cache_read_input_tokens",
    "cacheWriteTokens": "cache_creation_input_tokens",
}
_CLAUDE_USAGE_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
)


def normalize_usage(raw: dict | None) -> dict:
    if not isinstance(raw, dict) or not raw:
        return {}

    values: dict[str, int] = {}
    for key in _CLAUDE_USAGE_KEYS:
        if key in raw:
            values[key] = int(raw[key])
    for cursor_key, claude_key in _CURSOR_USAGE_KEYS.items():
        if cursor_key in raw and claude_key not in values:
            values[claude_key] = int(raw[cursor_key])

    if not values:
        return {}

    return {
        "input_tokens": values.get("input_tokens", 0),
        "output_tokens": values.get("output_tokens", 0),
        "cache_creation_input_tokens": values.get("cache_creation_input_tokens", 0),
        "cache_read_input_tokens": values.get("cache_read_input_tokens", 0),
    }


def usage_has_data(usage: dict) -> bool:
    return bool(usage)


def _usage_breakdown(usage: dict) -> tuple[int, int, int, int, int]:
    input_t = usage.get("input_tokens", 0)
    cache_cr = usage.get("cache_creation_input_tokens", 0)
    cache_rd = usage.get("cache_read_input_tokens", 0)
    output_t = usage.get("output_tokens", 0)
    total_t = input_t + cache_cr + cache_rd + output_t
    return input_t, cache_cr, cache_rd, output_t, total_t


def _format_usage_metrics(usage: dict, provider: str | None, *, spaced: bool) -> str:
    input_t, cache_cr, cache_rd, output_t, total_t = _usage_breakdown(usage)
    sep = "  " if spaced else " "
    parts = [f"input={input_t:,}"]
    if provider != "cursor":
        parts.append(f"cache_creation={cache_cr:,}")
    parts.extend(
        [
            f"cache_read={cache_rd:,}",
            f"output={output_t:,}",
            f"total={total_t:,}",
        ]
    )
    return sep.join(parts)


def format_usage_line(
    label: str, usage: dict, cost: float | None, provider: str | None = None
) -> str:
    if not usage_has_data(usage):
        return f"  [{label}] usage: not available"
    cost_str = f" / cost=${cost:.4f}" if cost is not None else ""
    metrics = _format_usage_metrics(usage, provider, spaced=False)
    return f"  [{label}] {metrics}{cost_str}"


def format_usage_report(
    label: str, usage: dict, cost: float | None, provider: str | None = None
) -> str:
    lines = [f"  [{label}]"]
    if not usage_has_data(usage):
        lines.append("    usage: not available")
    else:
        metrics = _format_usage_metrics(usage, provider, spaced=True)
        lines.append(f"    {metrics}")
    if cost is not None:
        lines.append(f"    cost=${cost:.4f}")
    return "\n".join(lines)


def format_usage_footer(total_cost: float, has_any_cost: bool) -> str:
    lines = ["  ----------------------------------------"]
    if has_any_cost:
        lines.append(f"  total cost: ${total_cost:.4f}")
    else:
        lines.append("  total cost: not available")
    return "\n".join(lines)


def format_usage_files_report(paths: list[str]) -> str:
    blocks: list[str] = []
    total_cost = 0.0
    has_any_cost = False
    for path in paths:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            continue
        label = data.get("label", path)
        usage = normalize_usage(data.get("usage"))
        cost = data.get("cost_usd")
        provider = data.get("provider")
        if provider is None:
            provider = resolve_provider()
        if cost is not None:
            total_cost += cost
            has_any_cost = True
        blocks.append(format_usage_report(label, usage, cost, provider))
    if not blocks:
        return format_usage_footer(0.0, False)
    return "\n".join(blocks + [format_usage_footer(total_cost, has_any_cost)])


def resolve_provider(provider: str | None = None) -> str:
    if provider is not None:
        normalized = provider.strip().lower()
        if normalized not in _VALID_PROVIDERS:
            raise ValueError(
                f"provider must be 'claude' or 'cursor', got {provider!r}"
            )
        return normalized

    env = os.environ.get("DAILY_BRIEF_LLM")
    if env is not None:
        normalized = env.strip().lower()
        if normalized not in _VALID_PROVIDERS:
            raise ValueError(
                f"DAILY_BRIEF_LLM must be 'claude' or 'cursor', got {env!r}"
            )
        return normalized

    if shutil.which("claude"):
        return "claude"
    if shutil.which("agent"):
        return "cursor"
    raise RuntimeError(
        "Neither 'claude' nor 'agent' found on PATH. "
        "Install Claude Code CLI (claude) or Cursor CLI (agent)."
    )


def resolve_model(role: str, provider: str) -> str:
    override = os.environ.get(_MODEL_ENV[role], "")
    if override:
        return override
    return _DEFAULT_MODELS[(role, provider)]


def call_llm(
    prompt: str,
    *,
    role: str,
    provider: str | None = None,
    run: Callable | None = None,
) -> tuple[str, dict, float | None]:
    if role not in _VALID_ROLES:
        raise ValueError(f"role must be 'select' or 'summarize', got {role!r}")
    resolved = resolve_provider(provider)
    model = resolve_model(role, resolved)
    if run is None:
        run = subprocess.run

    if resolved == "claude":
        cmd = _claude_cmd(role, model, prompt)
        return _invoke(cmd, "claude", run)

    tmpdir = tempfile.mkdtemp()
    try:
        cmd = _cursor_cmd(model, prompt, tmpdir)
        return _invoke(cmd, "agent", run)
    finally:
        try:
            shutil.rmtree(tmpdir)
        except OSError:
            pass


def _claude_cmd(role: str, model: str, prompt: str) -> list[str]:
    cmd = [
        "claude",
        "--model",
        model,
    ]
    if role == "select":
        cmd.extend(["--effort", "medium"])
    cmd.extend(
        [
            "--dangerously-skip-permissions",
            "--output-format",
            "json",
            "-p",
            prompt,
        ]
    )
    return cmd


def _cursor_cmd(model: str, prompt: str, workspace: str) -> list[str]:
    return [
        "agent",
        "-p",
        "--mode",
        "ask",
        "--trust",
        "--output-format",
        "json",
        "--model",
        model,
        "--workspace",
        workspace,
        "--",
        prompt,
    ]


def _invoke(
    cmd: list[str], binary: str, run: Callable
) -> tuple[str, dict, float | None]:
    result = run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"{binary} exited with {result.returncode}")

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON from {binary}") from exc

    if data.get("is_error"):
        raise RuntimeError(f"{binary} error: {data.get('result')}")

    raw_usage = data.get("usage")
    usage = normalize_usage(raw_usage if isinstance(raw_usage, dict) else None)
    cost_raw = data.get("total_cost_usd")
    if cost_raw is None:
        cost_raw = data.get("cost_usd")
    cost = float(cost_raw) if cost_raw is not None else None
    return str(data["result"]), usage, cost
