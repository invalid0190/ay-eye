"""
Tests for the Conversational Debugger.

Every layer is exercised through injected fakes — no real OCR, no real
LLM, no real foreground window probe.

Run:
    .venv\\Scripts\\python scripts\\test_code_debugger.py
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.engine.code_debugger import (
    CodeDebugger,
    CodeError,
    DebugResult,
    DebugSuggestion,
    IDEContext,
    IDEDetector,
    SuggestionCache,
    build_debug_prompt,
    extract_error,
    parse_debug_response,
    _looks_like_filename,
)


PASS: list[str] = []
FAIL: list[str] = []


def check(cond: bool, label: str) -> None:
    tag = "[PASS]" if cond else "[FAIL]"
    print(f"{tag} {label}")
    (PASS if cond else FAIL).append(label)


# ── Synthetic foreground probe ──────────────────────────────────────


@dataclass
class _Snap:
    title: str = ""
    process_name: str = ""


class FakeProbe:
    def __init__(self, title="", process_name=""):
        self._snap = _Snap(title=title, process_name=process_name)

    def snapshot(self):
        return self._snap


# ── IDEDetector ─────────────────────────────────────────────────────


def test_ide_classify_recognises_vscode():
    check(IDEDetector.classify("brain.py - Visual Studio Code") == "vscode",
          "VS Code title classified as 'vscode'")


def test_ide_classify_recognises_cursor_and_pycharm():
    check(IDEDetector.classify("main.ts — Cursor") == "cursor",
          "Cursor title classified as 'cursor'")
    check(IDEDetector.classify("PyCharm 2024.1.2 — ay-eye") == "pycharm",
          "PyCharm title classified as 'pycharm'")


def test_ide_classify_falls_back_to_unknown():
    check(IDEDetector.classify("Twitter / X - Google Chrome") == "unknown",
          "non-IDE title classified as 'unknown'")
    check(IDEDetector.classify("") == "unknown",
          "empty title classified as 'unknown'")


def test_ide_classify_uses_process_name_when_title_blank():
    check(IDEDetector.classify("", "Code.exe") == "vscode",
          "process name picks up VS Code when title is blank")


def test_ide_detect_via_probe_returns_full_context():
    det = IDEDetector(probe=FakeProbe(title="brain.py - Visual Studio Code",
                                      process_name="Code.exe"))
    ctx = det.detect()
    check(ctx.kind == "vscode" and ctx.is_known(),
          "detect() returns IDEContext with kind='vscode'")


def test_ide_detect_returns_unknown_when_probe_blank():
    det = IDEDetector(probe=FakeProbe(title="", process_name=""))
    ctx = det.detect()
    check(ctx.kind == "unknown" and not ctx.is_known(),
          "blank probe yields IDEContext(kind='unknown')")


# ── _looks_like_filename ───────────────────────────────────────────


def test_filename_matcher_python_traceback():
    out = _looks_like_filename('  File "/Users/foo/bar.py", line 42, in <module>')
    check(out is not None and out[0].endswith("bar.py") and out[1] == "42",
          "Python traceback line yields filename + line number")


def test_filename_matcher_typescript_columned():
    out = _looks_like_filename("src/components/App.tsx:23:14 - error TS2345")
    check(out is not None and out[0].endswith("App.tsx") and out[1] == "23",
          "TypeScript col:line file reference parsed")


def test_filename_matcher_returns_none_when_no_match():
    check(_looks_like_filename("just some code") is None,
          "non-filename line returns None")


# ── extract_error ──────────────────────────────────────────────────


def test_extract_error_python_traceback():
    text = """
def hello():
    return greet()

Traceback (most recent call last):
  File "/tmp/app.py", line 12, in <module>
    hello()
  File "/tmp/app.py", line 9, in hello
    return greet()
NameError: name 'greet' is not defined
""".strip()
    err = extract_error(text)
    check(err is not None,
          "Python traceback is detected")
    assert err is not None  # for type narrowing
    check(err.pattern_kind == "python_traceback",
          f"pattern_kind labelled 'python_traceback' (got {err.pattern_kind})")
    check("NameError" in err.error_text,
          "error stanza includes the actual exception line")
    check(err.file_hint.endswith("app.py") and err.line_hint == "12",
          f"file/line hint extracted (got {err.file_hint}:{err.line_hint})")


def test_extract_error_typescript():
    text = (
        "import { x } from './x';\n"
        "\n"
        "src/App.tsx:23:14 - error TS2345: Argument of type 'string' is "
        "not assignable to parameter of type 'number'.\n"
    )
    err = extract_error(text)
    check(err is not None and err.pattern_kind == "ts_error",
          "TypeScript TS2345 error detected and kind='ts_error'")
    assert err is not None
    check("TS2345" in err.error_text,
          "TS error code preserved in stanza")


def test_extract_error_javascript_runtime():
    text = "ReferenceError: foo is not defined\n    at <anonymous>:1:1"
    err = extract_error(text)
    check(err is not None and err.pattern_kind == "js_error",
          "ReferenceError detected as js_error")


def test_extract_error_picks_latest_when_multiple_present():
    text = (
        "TypeError: cannot read property 'x' of undefined\n"
        "...\n"
        "Some unrelated logs\n"
        "\n"
        "ReferenceError: bar is not defined\n"
    )
    err = extract_error(text)
    check(err is not None and "ReferenceError" in err.error_text,
          "later error wins when multiple anchors present in OCR")


def test_extract_error_returns_none_when_clean():
    text = "All systems nominal.\nProcess complete in 0.42s."
    check(extract_error(text) is None,
          "no error pattern -> returns None")


def test_extract_error_returns_none_for_empty_input():
    check(extract_error("") is None,
          "empty string -> None")
    check(extract_error("   \n   \n") is None,
          "whitespace-only -> None")
    check(extract_error(None) is None,  # type: ignore[arg-type]
          "non-string -> None")


def test_extract_error_includes_surrounding_code_context():
    text = (
        "function add(a, b) {\n"
        "  return a + b;\n"
        "}\n"
        "\n"
        "TypeError: Cannot read property 'x' of undefined\n"
    )
    err = extract_error(text)
    check(err is not None,
          "error detected in JS-like context")
    assert err is not None
    check(any("function add" in line for line in err.surrounding_lines),
          "surrounding_lines includes the function definition above the error")


def test_extract_error_truncates_at_max_lines():
    """Stanzas longer than the cap should not blow up."""
    long = "Traceback (most recent call last):\n" + "\n".join(
        f"  line {i}" for i in range(100)
    )
    err = extract_error(long)
    check(err is not None,
          "extract_error handles a 100-line stanza without crashing")


def test_extract_error_fingerprint_is_stable_across_calls():
    text = "ReferenceError: x is not defined"
    a = extract_error(text)
    b = extract_error(text)
    assert a is not None and b is not None
    check(a.fingerprint == b.fingerprint and len(a.fingerprint) == 12,
          "same input -> same 12-char fingerprint")


# ── build_debug_prompt ──────────────────────────────────────────────


def test_build_prompt_carries_pattern_kind_and_file_hint():
    err = CodeError(
        error_text="NameError: name 'greet' is not defined",
        surrounding_lines=["def hello():"],
        file_hint="/tmp/app.py", line_hint="12",
        pattern_kind="python_traceback",
    )
    ide = IDEContext(kind="vscode", title="app.py - VS Code", process_name="Code.exe")
    prompt = build_debug_prompt(err, ide)
    check("vscode" in prompt["user"],
          "prompt includes the IDE kind")
    check("python_traceback" in prompt["user"],
          "prompt includes pattern_kind for the LLM to specialise on")
    check("/tmp/app.py" in prompt["user"] and "12" in prompt["user"],
          "file + line hints surfaced to the LLM")


def test_build_prompt_demands_strict_json_response():
    prompt = build_debug_prompt(
        CodeError(error_text="x", surrounding_lines=[]),
        IDEContext(kind="vscode", title="", process_name=""),
    )
    check('"explanation"' in prompt["system"]
          and '"fix_steps"' in prompt["system"]
          and '"code_patch"' in prompt["system"]
          and '"confidence"' in prompt["system"],
          "system prompt declares all four required JSON keys")
    check("Do not include any prose outside the JSON object" in prompt["system"],
          "system prompt forbids prose around the JSON")


def test_build_prompt_omits_missing_hints_gracefully():
    err = CodeError(error_text="generic", surrounding_lines=[])
    prompt = build_debug_prompt(err, IDEContext(kind="vscode", title="", process_name=""))
    check("FILE_HINT" not in prompt["user"],
          "no FILE_HINT line when no file is known")
    check("LINE_HINT" not in prompt["user"],
          "no LINE_HINT line when no line is known")


# ── parse_debug_response ────────────────────────────────────────────


def test_parse_response_extracts_clean_json():
    raw = (
        '{"explanation":"x is undefined because import is missing",'
        '"fix_steps":["Import x at the top","Re-run"],"code_patch":"",'
        '"confidence":0.85}'
    )
    s = parse_debug_response(raw)
    check(s is not None,
          "valid JSON yields a DebugSuggestion")
    assert s is not None
    check(s.explanation.startswith("x is undefined"),
          "explanation extracted")
    check(s.fix_steps == ["Import x at the top", "Re-run"],
          "fix_steps extracted as list")
    check(abs(s.confidence - 0.85) < 1e-6,
          "confidence cast to float")


def test_parse_response_strips_markdown_fence():
    raw = (
        "```json\n"
        '{"explanation":"e","fix_steps":["f"],"code_patch":"","confidence":0.5}\n'
        "```"
    )
    s = parse_debug_response(raw)
    check(s is not None and s.explanation == "e",
          "JSON inside markdown fence is recovered")


def test_parse_response_clamps_confidence_to_zero_one():
    raw = (
        '{"explanation":"e","fix_steps":[],"code_patch":"",'
        '"confidence":2.5}'
    )
    s = parse_debug_response(raw)
    check(s is not None and s.confidence == 1.0,
          "confidence > 1 is clamped to 1.0")
    raw2 = (
        '{"explanation":"e","fix_steps":[],"code_patch":"",'
        '"confidence":-3}'
    )
    s2 = parse_debug_response(raw2)
    check(s2 is not None and s2.confidence == 0.0,
          "confidence < 0 is clamped to 0.0")


def test_parse_response_returns_none_for_empty_explanation():
    raw = '{"explanation":"","fix_steps":["x"],"code_patch":"","confidence":0.5}'
    check(parse_debug_response(raw) is None,
          "missing explanation -> None (no useful suggestion)")


def test_parse_response_returns_none_for_garbage():
    check(parse_debug_response("just some prose") is None,
          "non-JSON prose -> None")
    check(parse_debug_response("") is None,
          "empty string -> None")


def test_parse_response_coerces_string_fix_steps_to_list():
    raw = (
        '{"explanation":"e","fix_steps":"single string instead of list",'
        '"code_patch":"","confidence":0.5}'
    )
    s = parse_debug_response(raw)
    check(s is not None and len(s.fix_steps) == 1,
          "fix_steps as a string gets coerced to a single-element list")


# ── SuggestionCache ────────────────────────────────────────────────


def test_cache_hit_returns_stored_suggestion():
    cache = SuggestionCache(ttl_s=60.0)
    sug = DebugSuggestion(explanation="e", fix_steps=["f"], code_patch="", confidence=0.9)
    cache.put("FP", sug, now=100.0)
    out = cache.get("FP", now=110.0)
    check(out is sug,
          "cache hit returns the same suggestion object within TTL")


def test_cache_expiry_removes_stale_entry():
    cache = SuggestionCache(ttl_s=60.0)
    sug = DebugSuggestion(explanation="e", fix_steps=[], code_patch="", confidence=0.5)
    cache.put("FP", sug, now=100.0)
    out = cache.get("FP", now=200.0)  # 100s later -> expired
    check(out is None,
          "expired cache entry returns None")


def test_cache_evicts_oldest_when_full():
    cache = SuggestionCache(ttl_s=600.0, max_entries=2)
    s1 = DebugSuggestion(explanation="1", fix_steps=[], code_patch="", confidence=0.1)
    s2 = DebugSuggestion(explanation="2", fix_steps=[], code_patch="", confidence=0.2)
    s3 = DebugSuggestion(explanation="3", fix_steps=[], code_patch="", confidence=0.3)
    cache.put("a", s1, now=100.0)
    cache.put("b", s2, now=110.0)
    cache.put("c", s3, now=120.0)  # should evict 'a'
    check(cache.get("a", now=130.0) is None,
          "oldest entry evicted when cache exceeds max_entries")
    check(cache.get("b", now=130.0) is s2 and cache.get("c", now=130.0) is s3,
          "newer entries survive eviction")


# ── CodeDebugger.run_once ──────────────────────────────────────────


def _make_debugger(
    ide_kind="vscode",
    ide_title="brain.py - Visual Studio Code",
    ocr_text="",
    llm_response='{"explanation":"e","fix_steps":["f"],"code_patch":"","confidence":0.8}',
    llm_should_raise=False,
    ocr_should_raise=False,
):
    """Build a CodeDebugger wired with stubs."""

    class _Det(IDEDetector):
        def detect(self):  # type: ignore[override]
            return IDEContext(kind=ide_kind, title=ide_title, process_name="")

    def _ocr():
        if ocr_should_raise:
            raise RuntimeError("OCR backend dead")
        return ocr_text

    def _llm(prompt):
        if llm_should_raise:
            raise RuntimeError("network down")
        return llm_response

    return CodeDebugger(
        ide_detector=_Det(),
        ocr_caller=_ocr,
        llm_caller=_llm,
    )


def test_run_once_skips_when_foreground_is_not_an_ide():
    dbg = _make_debugger(ide_kind="unknown", ide_title="Twitter / X - Chrome")
    res = dbg.run_once()
    check(res.suggestion is None and res.skipped_reason == "not_an_ide",
          "non-IDE foreground -> skipped_reason='not_an_ide'")


def test_run_once_skips_when_no_error_in_view():
    dbg = _make_debugger(ocr_text="def hello():\n    return 'ok'\n")
    res = dbg.run_once()
    check(res.suggestion is None and res.skipped_reason == "no_error_in_view",
          "OCR text without an error pattern -> skipped_reason='no_error_in_view'")


def test_run_once_happy_path_yields_suggestion():
    dbg = _make_debugger(ocr_text=(
        "def hello():\n    return greet()\n\n"
        "Traceback (most recent call last):\n"
        '  File "/tmp/app.py", line 12, in <module>\n'
        "NameError: name 'greet' is not defined\n"
    ))
    res = dbg.run_once()
    check(res.suggestion is not None,
          "happy path produces a DebugSuggestion")
    assert res.suggestion is not None
    check(res.suggestion.explanation == "e",
          "suggestion's explanation matches the parsed LLM reply")
    check(res.error is not None and "NameError" in res.error.error_text,
          "DebugResult includes the detected error")
    check(res.from_cache is False,
          "first call is NOT marked as from_cache")


def test_run_once_returns_cached_on_second_call():
    dbg = _make_debugger(ocr_text=(
        "ReferenceError: foo is not defined\n"
    ))
    first = dbg.run_once()
    second = dbg.run_once()
    check(first.suggestion is not None,
          "first call produces a fresh suggestion")
    check(second.from_cache is True,
          "second call with the same error is served from cache")
    check(second.suggestion is first.suggestion,
          "cached suggestion is the exact same object")


def test_run_once_handles_ocr_exception():
    dbg = _make_debugger(ocr_should_raise=True)
    res = dbg.run_once()
    check(res.suggestion is None and res.skipped_reason.startswith("ocr_error"),
          "OCR exception is captured and surfaced via skipped_reason")


def test_run_once_handles_llm_exception():
    dbg = _make_debugger(
        ocr_text="ReferenceError: foo is not defined\n",
        llm_should_raise=True,
    )
    res = dbg.run_once()
    check(res.suggestion is None and res.skipped_reason.startswith("llm_error"),
          "LLM exception captured into skipped_reason without crashing")


def test_run_once_handles_llm_unparseable_reply():
    dbg = _make_debugger(
        ocr_text="ReferenceError: foo is not defined\n",
        llm_response="🤷",
    )
    res = dbg.run_once()
    check(res.suggestion is None and res.skipped_reason == "llm_unparseable",
          "unparseable LLM reply -> skipped_reason='llm_unparseable'")


def test_run_once_skips_when_no_ocr_caller():
    """If neither caller-supplied nor default OCR resolves, skip cleanly."""

    class _NoneIDE(IDEDetector):
        def detect(self):  # type: ignore[override]
            return IDEContext(kind="vscode", title="VS Code", process_name="")

    dbg = CodeDebugger(ide_detector=_NoneIDE(), ocr_caller=None, llm_caller=lambda p: "")
    # Force the default OCR resolver to fail by monkey-patching.
    def _no_ocr():
        return None
    dbg._resolve_ocr = lambda: None  # type: ignore[method-assign]
    res = dbg.run_once()
    check(res.suggestion is None and res.skipped_reason == "ocr_unavailable",
          "skipped_reason='ocr_unavailable' when no OCR backend is wired")


# ── Schema integration ────────────────────────────────────────────


def test_schema_accepts_debug_visible_error_action():
    from core.engine.response_schema import response_schema
    out = response_schema.validate({
        "intent": "act",
        "status": "in_progress",
        "message": "Looking at the error.",
        "actions": [{"type": "debug_visible_error"}],
        "confidence": 0.9,
    })
    check(out["valid"] is True,
          "schema accepts debug_visible_error with no fields")
    check(len(out["response"]["actions"]) == 1,
          "action survives validation")


def test_response_format_enum_includes_debug_visible_error():
    from core.engine.response_format import build_action_schema
    enum = set(build_action_schema()["properties"]["type"]["enum"])
    check("debug_visible_error" in enum,
          "JSON Schema enum lists debug_visible_error for structured outputs")


# ── Run ───────────────────────────────────────────────────────────


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print()
    print(f"=== Code Debugger: {len(PASS)} passed, {len(FAIL)} failed ===")
    if FAIL:
        for line in FAIL:
            print(f"  - {line}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
