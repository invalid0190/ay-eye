"""
Response format / structured outputs for the LLM.

Builds the ``response_format`` payload sent to the LLM provider so the model
returns a JSON object that conforms to our Brain schema *natively*. This
eliminates ~95% of "JSON parse failed, retrying..." turns the healing parser
used to absorb.

Supported tiers (best -> worst):

  1. **OpenAI strict JSON Schema** (gpt-4o / gpt-4o-mini / gpt-4.1*):
     ``response_format = {"type": "json_schema", "json_schema": {...},
                          "strict": true}``
     The model is *guaranteed* to return JSON matching the schema.

  2. **JSON object mode** (other OpenAI-compatible providers, Moonshot/Kimi,
     AgentRouter, etc.):
     ``response_format = {"type": "json_object"}``
     Model returns valid JSON; we still rely on ``ResponseSchemaValidator``
     for shape validation.

  3. **Ollama "format: json"**: handled by the bridge directly (no
     ``response_format`` field).

The Python ``ResponseSchemaValidator`` in ``core/engine/response_schema.py``
remains the source of truth for *semantic* validity; this module only
shapes the wire payload so the model gives us syntactically correct JSON
in the first place. Fields are intentionally permissive — every per-action
field is nullable — and per-action-type required fields are enforced
downstream by the validator. Trying to express the union of all action
shapes in strict-mode JSON Schema requires ``anyOf``, which complicates
the schema for marginal benefit and is rejected by some compatible
providers.

Models that do NOT support strict schemas are detected by name prefix; if
in doubt we degrade to ``json_object`` mode rather than risk a 400.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from core.engine.response_schema import (
    _VALID_ACTION_TYPES,
    _VALID_EXPECT_TYPES,
    _VALID_INTENTS,
    _VALID_STATUSES,
)


# Models known to support OpenAI's strict JSON Schema response_format.
# Prefix match is intentional so future point-releases (gpt-4o-2024-11-20,
# gpt-4o-mini-2024-07-18, etc.) are picked up automatically.
_STRICT_SCHEMA_OPENAI_MODELS = (
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
    "o1",
    "o3",
    "o4-mini",
)


def supports_strict_schema(provider: str, model: str) -> bool:
    """Return True if the (provider, model) pair supports strict JSON Schema."""
    if provider != "openai" or not model:
        return False
    m = model.lower()
    return any(m.startswith(prefix) for prefix in _STRICT_SCHEMA_OPENAI_MODELS)


def _str_or_null() -> Dict[str, Any]:
    return {"type": ["string", "null"]}


def _num_or_null() -> Dict[str, Any]:
    return {"type": ["number", "null"]}


def _array_of_strings_or_null() -> Dict[str, Any]:
    return {
        "type": ["array", "null"],
        "items": {"type": "string"},
    }


def build_action_schema() -> Dict[str, Any]:
    """JSON Schema for a single action object.

    All per-action fields are nullable — the Python validator enforces the
    type-specific 'required' set downstream. We list every common field so
    the strict schema accepts every action variant our executor handles.
    """
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "type": {
                "type": "string",
                "enum": sorted(_VALID_ACTION_TYPES),
                "description": "Action kind. Determines which of the other fields are required.",
            },
            # Coordinates / target.
            "x": _num_or_null(),
            "y": _num_or_null(),
            "x1": _num_or_null(),
            "y1": _num_or_null(),
            "x2": _num_or_null(),
            "y2": _num_or_null(),
            "target": _str_or_null(),
            "text": _str_or_null(),
            "keys": _array_of_strings_or_null(),
            "key": _str_or_null(),
            "amount": _num_or_null(),
            # Process / shell.
            "command": _str_or_null(),
            "path": _str_or_null(),
            "content": _str_or_null(),
            "url": _str_or_null(),
            "app": _str_or_null(),
            # Skill / Blender extras.
            "name": _str_or_null(),
            "instruction": _str_or_null(),
            "script": _str_or_null(),
            "description": _str_or_null(),
            # arrange_windows extras.
            "preset": _str_or_null(),
            "monitor_index": _num_or_null(),
            # Optional verification contract.
            "expect": {
                "type": ["object", "null"],
                "additionalProperties": False,
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": sorted(_VALID_EXPECT_TYPES),
                    },
                    "value": _str_or_null(),
                    "timeout": _num_or_null(),
                },
                "required": ["type", "value", "timeout"],
            },
        },
        # OpenAI strict mode requires every property in required.
        "required": [
            "type", "x", "y", "x1", "y1", "x2", "y2", "target", "text",
            "keys", "key", "amount", "command", "path", "content", "url",
            "app", "name", "instruction", "script", "description",
            "preset", "monitor_index", "expect",
        ],
    }


def build_brain_schema() -> Dict[str, Any]:
    """Top-level Brain response schema."""
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "intent": {
                "type": "string",
                "enum": sorted(_VALID_INTENTS),
            },
            "status": {
                "type": "string",
                "enum": sorted(_VALID_STATUSES),
            },
            "message": {"type": "string"},
            "speech": _str_or_null(),
            "confidence": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
            },
            "plan": _array_of_strings_or_null(),
            "actions": {
                "type": "array",
                "items": build_action_schema(),
            },
        },
        "required": [
            "intent", "status", "message", "speech",
            "confidence", "plan", "actions",
        ],
    }


def build_response_format(provider: str, model: str) -> Optional[Dict[str, Any]]:
    """Return the right ``response_format`` payload for (provider, model).

    Returns ``None`` for providers that should not set ``response_format``
    at all (e.g. local Ollama uses ``format: json`` on the request body,
    Anthropic uses forced tool-use which lives on a different request key).
    """
    if provider == "openai" and supports_strict_schema(provider, model):
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "ay_eye_brain_response",
                "strict": True,
                "schema": build_brain_schema(),
            },
        }
    if provider in ("openai", "moonshot", "agentrouter"):
        # Compatible JSON-object mode keeps the model honest without
        # demanding a schema the provider may not implement.
        return {"type": "json_object"}
    return None


# ── Anthropic tool-calling -------------------------------------------

# Anthropic does not have an OpenAI-style ``response_format``. To get
# guaranteed structured JSON we expose the brain schema as a *tool* and
# instruct the model to use it (``tool_choice = {"type":"tool", "name":...}``).
# The model then emits a ``tool_use`` content block whose ``input`` is a
# dict already matching our schema.

_BRAIN_TOOL_NAME = "respond_to_user"


def build_anthropic_tools() -> list[Dict[str, Any]]:
    """Tool definition Anthropic models call to deliver a structured reply."""
    return [
        {
            "name": _BRAIN_TOOL_NAME,
            "description": (
                "Return your structured response to the user's command. "
                "Always call this tool exactly once. Do NOT reply with prose."
            ),
            "input_schema": build_brain_schema(),
        }
    ]


def build_anthropic_tool_choice() -> Dict[str, Any]:
    """Force the model to invoke the brain tool (no free-text fallback)."""
    return {"type": "tool", "name": _BRAIN_TOOL_NAME}


def is_anthropic_brain_tool(name: str) -> bool:
    return name == _BRAIN_TOOL_NAME
