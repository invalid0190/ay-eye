"""Regression tests for the Anthropic Claude provider in LLMBridge.

These tests do NOT hit the real Anthropic API. They use a fake ``requests``
module to verify:

  1. LLM_PROVIDER=anthropic + ANTHROPIC_API_KEY routes to the Anthropic
     branch, with the right URL, headers, and forced tool-use payload.
  2. The brain dict is extracted from the ``tool_use`` content block.
  3. Vision requests embed images as base64 content blocks (NOT image_url).
  4. Token usage from Anthropic's ``input_tokens``/``output_tokens`` fields
     is recorded by telemetry without raising.
  5. Provider priority: explicit LLM_PROVIDER beats key-only autodetect.

Run:
    .venv\\Scripts\\python scripts\\test_anthropic_provider.py
"""

from __future__ import annotations

import json
import os
import sys
import types
import importlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS: list[str] = []
FAIL: list[str] = []


def check(condition, label):
    if condition:
        PASS.append(label)
        print(f"[PASS] {label}")
    else:
        FAIL.append(label)
        print(f"[FAIL] {label}")


# ── Test infra ────────────────────────────────────────────────────────


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text or json.dumps(self._json)

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}: {self.text}")


class _RequestRecorder:
    def __init__(self, response: _FakeResponse):
        self.response = response
        self.calls: list[dict] = []

    def post(self, url, json=None, headers=None, timeout=None, **kw):
        self.calls.append({
            "url": url, "json": json, "headers": headers or {}, "timeout": timeout,
        })
        return self.response


_DOTENV_PATCHED = False


def _patch_dotenv_at_source():
    """Make ``dotenv.load_dotenv`` a no-op for the rest of the test process.

    Patching the real module means that any future ``from dotenv import
    load_dotenv`` (including the one inside ``importlib.reload(llm_bridge)``)
    binds to the no-op stub, so the project's real ``.env`` cannot leak
    into the dispatch tests.
    """
    global _DOTENV_PATCHED
    if _DOTENV_PATCHED:
        return
    import dotenv
    dotenv.load_dotenv = lambda *a, **kw: False
    dotenv.main.load_dotenv = lambda *a, **kw: False
    _DOTENV_PATCHED = True


def _fresh_bridge_with_anthropic_only(monkeypatch_env: dict):
    """Reload llm_bridge with a controlled environment.

    Returns the **already-imported module** with its env in the patched
    state, deferring cleanup until ``_restore_env(state)`` is called.
    The bridge constructor reads ``os.environ`` at call time, so callers
    must instantiate ``LLMBridge()`` BEFORE invoking the returned cleanup
    or the original env will leak back in.

    Usage:
        mod, cleanup = _fresh_bridge_with_anthropic_only({...})
        try:
            b = mod.LLMBridge()
            ...
        finally:
            cleanup()
    """
    _patch_dotenv_at_source()
    keys_to_wipe = (
        "OPENAI_API_KEY", "MOONSHOT_API_KEY", "KIMI_API_KEY",
        "AGENT_ROUTER_API_KEY", "OLLAMA_API_KEY",
        "ANTHROPIC_API_KEY", "CLAUDE_API_KEY",
        "LLM_PROVIDER", "ANTHROPIC_MODEL",
    )
    saved = {k: os.environ.get(k) for k in keys_to_wipe}
    for k in keys_to_wipe:
        os.environ.pop(k, None)
    for k, v in monkeypatch_env.items():
        os.environ[k] = v

    import core.engine.llm_bridge as bridge_mod
    importlib.reload(bridge_mod)

    def cleanup():
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    return bridge_mod, cleanup


def _make_bridge(monkeypatch_env: dict):
    """Convenience: set up env, reload, instantiate LLMBridge, then restore.

    Returns ``(bridge_instance, module)`` so tests can patch
    ``module.requests`` for HTTP assertions while still getting a fully
    constructed bridge. Env is restored before this function returns.
    """
    mod, cleanup = _fresh_bridge_with_anthropic_only(monkeypatch_env)
    try:
        bridge = mod.LLMBridge()
    finally:
        cleanup()
    return bridge, mod


# ── Provider dispatch ─────────────────────────────────────────────────


def test_anthropic_routed_when_provider_explicit():
    b, _ = _make_bridge({
        "LLM_PROVIDER": "anthropic",
        "ANTHROPIC_API_KEY": "sk-ant-fake-test-key",
    })
    check(b.provider == "anthropic", "LLM_PROVIDER=anthropic -> provider=anthropic")
    check(b.url == "https://api.anthropic.com/v1/messages",
          "Anthropic uses /v1/messages endpoint")
    check(b.model.startswith("claude"),
          f"Anthropic default model is a claude variant (got {b.model})")


def test_anthropic_picked_up_by_claude_alias():
    b, _ = _make_bridge({
        "LLM_PROVIDER": "claude",  # alternate spelling
        "ANTHROPIC_API_KEY": "sk-ant-fake-test-key",
    })
    check(b.provider == "anthropic", "LLM_PROVIDER=claude alias -> provider=anthropic")


def test_openai_wins_when_both_keys_present_and_no_explicit_provider():
    b, _ = _make_bridge({
        "OPENAI_API_KEY": "sk-openai-fake",
        "ANTHROPIC_API_KEY": "sk-ant-fake",
    })
    check(b.provider == "openai",
          "OpenAI wins by default when both keys present (preserves existing UX)")


def test_anthropic_autodetected_when_only_anthropic_key_set():
    b, _ = _make_bridge({
        "ANTHROPIC_API_KEY": "sk-ant-fake",
    })
    check(b.provider == "anthropic",
          "Anthropic is auto-selected when it is the only configured provider")


# ── Headers ───────────────────────────────────────────────────────────


def test_anthropic_headers_use_x_api_key_and_version():
    b, _ = _make_bridge({
        "LLM_PROVIDER": "anthropic",
        "ANTHROPIC_API_KEY": "sk-ant-fake",
    })
    h = b._build_headers()
    check(h.get("x-api-key") == "sk-ant-fake",
          "x-api-key header set to the Anthropic key")
    check(h.get("anthropic-version", "").strip() != "",
          "anthropic-version header is non-empty")
    check("Authorization" not in h,
          "Anthropic does NOT use Bearer Authorization header")


# ── Payload shape (text + vision) ─────────────────────────────────────


def test_anthropic_text_payload_uses_forced_tool_use(monkeypatch_required=True):
    b, mod = _make_bridge({
        "LLM_PROVIDER": "anthropic",
        "ANTHROPIC_API_KEY": "sk-ant-fake",
    })

    fake = _FakeResponse(status_code=200, json_data={
        "content": [{
            "type": "tool_use",
            "name": "respond_to_user",
            "input": {
                "intent": "guide", "status": "complete", "message": "hi",
                "speech": None, "confidence": 0.9, "plan": None, "actions": [],
            },
        }],
        "usage": {"input_tokens": 50, "output_tokens": 12},
    })
    rec = _RequestRecorder(fake)
    mod.requests = rec  # patch the module-level requests

    out = b._complete_prompt_text("hello", retry=False)
    check(out is not None and out.get("intent") == "guide",
          "tool_use input dict returned to caller verbatim")
    if not rec.calls:
        check(False, "Anthropic POST was issued")
        return
    call = rec.calls[0]
    payload = call["json"]
    check(payload.get("model", "").startswith("claude"),
          "Anthropic payload carries claude model")
    check(isinstance(payload.get("tools"), list) and payload["tools"],
          "Anthropic payload includes a 'tools' list")
    check(payload.get("tool_choice", {}).get("type") == "tool",
          "tool_choice forces a specific tool")
    check(payload.get("tool_choice", {}).get("name") == "respond_to_user",
          "tool_choice points at the brain tool")
    check("max_tokens" in payload,
          "Anthropic requires max_tokens (we set a default)")


def test_anthropic_vision_payload_uses_base64_image_blocks():
    b, mod = _make_bridge({
        "LLM_PROVIDER": "anthropic",
        "ANTHROPIC_API_KEY": "sk-ant-fake",
    })

    fake = _FakeResponse(status_code=200, json_data={
        "content": [{
            "type": "tool_use",
            "name": "respond_to_user",
            "input": {
                "intent": "act", "status": "complete", "message": "ok",
                "speech": None, "confidence": 0.95, "plan": None,
                "actions": [{"type": "click", "x": 100, "y": 200,
                             "x1": None, "y1": None, "x2": None, "y2": None,
                             "target": None, "text": None, "keys": None,
                             "key": None, "amount": None, "command": None,
                             "path": None, "content": None, "url": None,
                             "app": None, "name": None, "instruction": None,
                             "script": None, "description": None, "expect": None}],
            },
        }],
        "usage": {"input_tokens": 200, "output_tokens": 20},
    })
    rec = _RequestRecorder(fake)
    mod.requests = rec

    fake_b64 = "ZmFrZS1qcGVnLWJ5dGVz"  # "fake-jpeg-bytes"
    out = b._generate_with_vision_internal("look at screen", [fake_b64], retry=False)
    check(out is not None and out.get("intent") == "act",
          "vision tool_use input returned to caller")
    if not rec.calls:
        check(False, "Anthropic vision POST was issued")
        return
    payload = rec.calls[0]["json"]
    msgs = payload.get("messages", [])
    check(len(msgs) == 1, "single user message")
    if not msgs:
        return
    content = msgs[0].get("content")
    check(isinstance(content, list), "vision content is a list of blocks")
    types_seen = [b.get("type") for b in content if isinstance(b, dict)]
    check("text" in types_seen and "image" in types_seen,
          f"vision payload mixes text + image blocks (got {types_seen})")
    img_block = next((b for b in content if isinstance(b, dict) and b.get("type") == "image"), None)
    if img_block is None:
        check(False, "image block present")
        return
    src = img_block.get("source", {})
    check(src.get("type") == "base64",
          "image block uses base64 source (NOT image_url like OpenAI)")
    check(src.get("data") == fake_b64,
          "image data is forwarded verbatim from caller")
    check(src.get("media_type", "").startswith("image/"),
          "media_type is set on the image source")


# ── Response parsing fallbacks ────────────────────────────────────────


def test_anthropic_parser_falls_back_to_text_if_no_tool_use():
    b, _ = _make_bridge({
        "LLM_PROVIDER": "anthropic",
        "ANTHROPIC_API_KEY": "sk-ant-fake",
    })
    # Some misbehaving model dropped tool_use and returned plain text JSON.
    out = b._parse_anthropic_response({
        "content": [{
            "type": "text",
            "text": '{"intent":"guide","status":"complete","message":"hi","actions":[],"confidence":0.5}',
        }],
    })
    check(isinstance(out, dict) and out.get("intent") == "guide",
          "healing parser recovers JSON from text-only Anthropic reply")


def test_anthropic_parser_returns_none_for_empty_content():
    b, _ = _make_bridge({
        "LLM_PROVIDER": "anthropic",
        "ANTHROPIC_API_KEY": "sk-ant-fake",
    })
    check(b._parse_anthropic_response({"content": []}) is None,
          "empty content -> None (caller will retry or surface error)")
    check(b._parse_anthropic_response({}) is None,
          "missing 'content' key -> None")


# ── Telemetry ─────────────────────────────────────────────────────────


def test_anthropic_token_usage_recorded():
    b, _ = _make_bridge({
        "LLM_PROVIDER": "anthropic",
        "ANTHROPIC_API_KEY": "sk-ant-fake",
    })
    # _record_usage should accept Anthropic's input_tokens/output_tokens shape
    # without raising. We can't easily assert telemetry state here, but a
    # silent run is the contract: never raise on the LLM hot path.
    try:
        b._record_usage(
            {"usage": {"input_tokens": 123, "output_tokens": 45}},
            duration_ms=500, vision=False,
        )
        ok = True
    except Exception:
        ok = False
    check(ok, "_record_usage handles Anthropic input_tokens/output_tokens without raising")


# ── Runner ────────────────────────────────────────────────────────────


def main():
    test_anthropic_routed_when_provider_explicit()
    test_anthropic_picked_up_by_claude_alias()
    test_openai_wins_when_both_keys_present_and_no_explicit_provider()
    test_anthropic_autodetected_when_only_anthropic_key_set()
    test_anthropic_headers_use_x_api_key_and_version()
    test_anthropic_text_payload_uses_forced_tool_use()
    test_anthropic_vision_payload_uses_base64_image_blocks()
    test_anthropic_parser_falls_back_to_text_if_no_tool_use()
    test_anthropic_parser_returns_none_for_empty_content()
    test_anthropic_token_usage_recorded()

    print(f"\n=== Anthropic provider: {len(PASS)} passed, {len(FAIL)} failed ===")
    if FAIL:
        for f in FAIL:
            print(f"  - {f}")
        sys.exit(1)


if __name__ == "__main__":
    main()
