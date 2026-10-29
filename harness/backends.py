"""Model backends. Each returns a dict with the same shape so the cache is backend-agnostic."""

import json
import subprocess
import tempfile
import time

MODEL_ALIASES = {"haiku": "haiku", "sonnet": "sonnet", "opus": "opus"}


class ClaudeCLIBackend:
    """Headless Claude Code (`claude -p`): clean system prompt, no tools, no MCP, no settings.

    Runs under the local user's Claude login. `costUSD` is reported by the CLI at
    list prices (costBasis: list), not as a bill.
    """

    name = "claude-cli"

    def __init__(self, binary="claude", timeout_s=300):
        self.binary = binary
        self.timeout_s = timeout_s

    def call(self, model, system, user):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=True) as f:
            f.write(system)
            f.flush()
            cmd = [
                self.binary, "-p",
                "--model", MODEL_ALIASES[model],
                "--system-prompt-file", f.name,
                "--tools", "",
                "--strict-mcp-config",
                "--setting-sources", "",
                "--no-session-persistence",
                "--output-format", "json",
            ]
            t0 = time.monotonic()
            proc = subprocess.run(cmd, input=user, capture_output=True, text=True, timeout=self.timeout_s)
            wall_ms = int((time.monotonic() - t0) * 1000)
        if proc.returncode != 0:
            raise RuntimeError(f"claude -p failed ({proc.returncode}): {proc.stderr[-500:]}")
        out = json.loads(proc.stdout)
        if out.get("is_error"):
            raise RuntimeError(f"claude -p returned an error: {str(out.get('result'))[:500]}")
        usage_by_model = out.get("modelUsage", {})
        canonical = next(iter(usage_by_model), None)
        u = out.get("usage", {})
        return {
            "text": out.get("result", ""),
            "canonical_model": canonical,
            "cost_usd": out.get("total_cost_usd"),
            "duration_api_ms": out.get("duration_api_ms"),
            "wall_ms": wall_ms,
            "usage": {
                "input_tokens": u.get("input_tokens", 0),
                "cache_creation_input_tokens": u.get("cache_creation_input_tokens", 0),
                "cache_read_input_tokens": u.get("cache_read_input_tokens", 0),
                "output_tokens": u.get("output_tokens", 0),
                "thinking_tokens": (u.get("output_tokens_details") or {}).get("thinking_tokens", 0),
            },
            "backend": self.name,
        }


class AnthropicAPIBackend:
    """Direct Messages API via the `anthropic` SDK. Same cache format; not used for the
    published numbers. Cost is computed from `prices` ($/MTok) supplied by the caller,
    because list prices change and must be checked at run time."""

    name = "anthropic-api"
    MODEL_IDS = {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5"}

    def __init__(self, prices, client=None, max_tokens=2048):
        if client is None:
            import anthropic  # optional dependency

            client = anthropic.Anthropic()
        self.client = client
        self.prices = prices
        self.max_tokens = max_tokens

    def call(self, model, system, user):
        t0 = time.monotonic()
        msg = self.client.messages.create(
            model=self.MODEL_IDS[model],
            max_tokens=self.max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
        )
        wall_ms = int((time.monotonic() - t0) * 1000)
        u = msg.usage
        usage = {
            "input_tokens": u.input_tokens,
            "cache_creation_input_tokens": u.cache_creation_input_tokens or 0,
            "cache_read_input_tokens": u.cache_read_input_tokens or 0,
            "output_tokens": u.output_tokens,
            "thinking_tokens": 0,
        }
        p = self.prices[model]
        cost = (
            usage["input_tokens"] * p["input"]
            + usage["cache_creation_input_tokens"] * p["cache_write"]
            + usage["cache_read_input_tokens"] * p["cache_read"]
            + usage["output_tokens"] * p["output"]
        ) / 1e6
        return {
            "text": "".join(b.text for b in msg.content if b.type == "text"),
            "canonical_model": msg.model,
            "cost_usd": cost,
            "duration_api_ms": wall_ms,
            "wall_ms": wall_ms,
            "usage": usage,
            "backend": self.name,
        }
