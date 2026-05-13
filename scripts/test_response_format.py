"""Regression tests for the structured-output response_format builder.

These tests verify that:
  1. Strict JSON Schema is selected for OpenAI gpt-4o-family models.
  2. Plain json_object mode is selected for other OpenAI-compatible providers.
  3. Ollama / unknown providers get None (use ``format: json`` body field).
  4. The generated brain schema covers every action type the validator
     accepts, so the LLM can return any of them without a 400.
  5. Strict-mode invariants hold: every property in 'required',
     additionalProperties = false at every object level, no spurious keys.

Run:
    .venv\\Scripts\\python scripts\\test_response_format.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.engine.response_format import (
    build_action_schema,
    build_brain_schema,
    build_response_format,
    supports_strict_schema,
)
from core.engine.response_schema import (
    _VALID_ACTION_TYPES,
    _VALID_EXPECT_TYPES,
    _VALID_INTENTS,
    _VALID_STATUSES,
)


PASS: list[str] = []
FAIL: list[str] = []


def check(condition: bool, label: str) -> None:
    if condition:
        PASS.append(label)
        print(f"[PASS] {label}")
    else:
        FAIL.append(label)
        print(f"[FAIL] {label}")


# ── supports_strict_schema ────────────────────────────────────────────


def test_strict_schema_picks_openai_gpt4o_family():
    check(supports_strict_schema("openai", "gpt-4o"),
          "gpt-4o supports strict schema")
    check(supports_strict_schema("openai", "gpt-4o-mini"),
          "gpt-4o-mini supports strict schema")
    check(supports_strict_schema("openai", "gpt-4o-2024-11-20"),
          "future gpt-4o point-release picked up by prefix match")
    check(supports_strict_schema("openai", "gpt-4.1"),
          "gpt-4.1 supports strict schema")


def test_strict_schema_rejects_other_providers_and_models():
    check(not supports_strict_schema("openai", "gpt-3.5-turbo"),
          "gpt-3.5-turbo does NOT use strict schema")
    check(not supports_strict_schema("moonshot", "kimi-k2.6"),
          "Moonshot does NOT use strict schema")
    check(not supports_strict_schema("agentrouter", "deepseek-v3.1"),
          "AgentRouter does NOT use strict schema")
    check(not supports_strict_schema("ollama", "gemma4:e2b"),
          "Ollama does NOT use strict schema")
    check(not supports_strict_schema("openai", ""),
          "Empty model string is rejected")


# ── build_response_format dispatch ────────────────────────────────────


def test_response_format_for_openai_strict_model():
    rf = build_response_format("openai", "gpt-4o")
    check(rf is not None, "gpt-4o returns a response_format")
    if rf is None:
        return
    check(rf.get("type") == "json_schema",
          "gpt-4o uses json_schema type")
    js = rf.get("json_schema", {})
    check(js.get("strict") is True,
          "json_schema marked strict=True")
    check(js.get("name") and isinstance(js["name"], str),
          "json_schema has a name")
    check("schema" in js and isinstance(js["schema"], dict),
          "json_schema has a schema dict")


def test_response_format_for_compatible_providers():
    for provider, model in [
        ("openai", "gpt-3.5-turbo"),
        ("moonshot", "kimi-k2.6"),
        ("agentrouter", "deepseek-v3.1"),
    ]:
        rf = build_response_format(provider, model)
        check(
            rf == {"type": "json_object"},
            f"{provider}/{model} -> json_object mode",
        )


def test_response_format_for_ollama_returns_none():
    check(build_response_format("ollama", "gemma4:e2b") is None,
          "Ollama returns None (uses format:json on body)")
    check(build_response_format("custom", "anything") is None,
          "Unknown provider returns None")


# ── Schema completeness ───────────────────────────────────────────────


def test_brain_schema_lists_every_intent_and_status():
    schema = build_brain_schema()
    intents = set(schema["properties"]["intent"]["enum"])
    statuses = set(schema["properties"]["status"]["enum"])
    check(intents == _VALID_INTENTS,
          f"intent enum matches validator (got {intents})")
    check(statuses == _VALID_STATUSES,
          f"status enum matches validator (got {statuses})")


def test_action_schema_lists_every_action_type():
    action = build_action_schema()
    types = set(action["properties"]["type"]["enum"])
    check(types == _VALID_ACTION_TYPES,
          f"action type enum matches validator ({len(types)} types)")


def test_expect_schema_lists_every_expect_type():
    action = build_action_schema()
    expect = action["properties"]["expect"]
    expect_types = set(expect["properties"]["type"]["enum"])
    check(expect_types == _VALID_EXPECT_TYPES,
          "expect.type enum matches validator")


# ── Strict-mode invariants (catch silent OpenAI 400s) ────────────────


def _walk_objects(node, path="$"):
    """Yield every JSON-Schema object node along with its path."""
    if isinstance(node, dict):
        if node.get("type") == "object" or "properties" in node:
            yield path, node
        for k, v in node.items():
            yield from _walk_objects(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk_objects(v, f"{path}[{i}]")


def test_every_object_has_additional_properties_false():
    schema = build_brain_schema()
    bad = []
    for path, obj in _walk_objects(schema):
        # Skip nodes that aren't really object schemas (e.g. {"type":["object","null"]})
        # but DO have properties — those still need additionalProperties: false.
        if "properties" not in obj:
            continue
        if obj.get("additionalProperties") is not False:
            bad.append(path)
    check(not bad,
          f"every object schema has additionalProperties: false (violations: {bad})")


def test_every_property_appears_in_required():
    """OpenAI strict mode rejects schemas where a property is not required."""
    schema = build_brain_schema()
    bad = []
    for path, obj in _walk_objects(schema):
        if "properties" not in obj:
            continue
        props = set(obj["properties"].keys())
        required = set(obj.get("required") or [])
        missing = props - required
        if missing:
            bad.append((path, sorted(missing)))
    check(not bad,
          f"every property is listed in 'required' (violations: {bad})")


def test_no_unsupported_keywords_in_strict_schema():
    """Strict mode forbids 'format', 'pattern', 'minLength' etc. We currently
    only use 'minimum'/'maximum' on confidence which IS allowed; this test
    guards against future drift."""
    forbidden = {"format", "pattern", "minLength", "maxLength", "default"}
    schema = build_brain_schema()
    bad = []
    for path, obj in _walk_objects(schema):
        for k in obj.keys():
            if k in forbidden:
                bad.append(f"{path}.{k}")
    check(not bad,
          f"no forbidden keywords used (violations: {bad})")


# ── Action coverage smoke test ────────────────────────────────────────


def test_action_schema_includes_required_fields_for_every_type():
    """For each action type our validator can demand fields for, the strict
    schema's action object must list those fields as nullable properties so
    the model is allowed to emit them."""
    from core.engine.response_schema import _ACTION_REQUIRED_FIELDS

    action = build_action_schema()
    props = set(action["properties"].keys())
    missing = []
    for a_type, fields in _ACTION_REQUIRED_FIELDS.items():
        for f in fields:
            if f not in props:
                missing.append(f"{a_type}.{f}")
    check(not missing,
          f"every per-action required field is present in the schema (missing: {missing})")


# ── Runner ────────────────────────────────────────────────────────────


def main():
    test_strict_schema_picks_openai_gpt4o_family()
    test_strict_schema_rejects_other_providers_and_models()
    test_response_format_for_openai_strict_model()
    test_response_format_for_compatible_providers()
    test_response_format_for_ollama_returns_none()
    test_brain_schema_lists_every_intent_and_status()
    test_action_schema_lists_every_action_type()
    test_expect_schema_lists_every_expect_type()
    test_every_object_has_additional_properties_false()
    test_every_property_appears_in_required()
    test_no_unsupported_keywords_in_strict_schema()
    test_action_schema_includes_required_fields_for_every_type()

    print(f"\n=== Response format: {len(PASS)} passed, {len(FAIL)} failed ===")
    if FAIL:
        for f in FAIL:
            print(f"  - {f}")
        sys.exit(1)


if __name__ == "__main__":
    main()
