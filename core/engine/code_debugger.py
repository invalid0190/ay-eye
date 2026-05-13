"""
Conversational Debugger
=======================

When the user asks "what's this error?" / "yeh kya hai" / "fix this",
the debugger:

1. Confirms an IDE is the foreground app.
2. Runs OCR over the IDE region of the screen.
3. Extracts the most recent error stanza from the OCR output (we look
   for canonical patterns like ``TypeError:``, ``Traceback (most recent
   call last)``, ``error TS2345``, ``ReferenceError``, etc.).
4. Pulls a chunk of surrounding code as context.
5. Asks the LLM for an explanation + suggested fix.
6. Returns a ``DebugSuggestion`` the executor can speak / log / show.

Design choices
--------------
* **On-demand, not always-on.** A polled / event-driven background
  watcher is doable but invasive (lots of LLM calls, privacy hits, UI
  noise). v1 fires only when the user explicitly asks.
* **OCR over squiggle detection.** Squiggles are visual — accurate
  detection needs a CV model. OCR catches the *text* of the error,
  which is what the LLM actually needs to suggest a fix.
* **Mockable everything.** ``IDEDetector``, ``OCREngine``, and
  ``LLMCaller`` are injected so unit tests run without real screens
  or API keys.
* **Result hashing.** Two consecutive calls on the same error stanza
  return the cached suggestion. Avoids burning tokens when the user
  repeatedly asks the same question.
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Optional, Protocol

from core.utils.logger import logger


# ── Public data types ────────────────────────────────────────────────


@dataclass
class IDEContext:
    """Information about the active IDE window."""

    kind: str  # "vscode", "cursor", "pycharm", "intellij", ...
    title: str
    process_name: str

    def is_known(self) -> bool:
        return self.kind != "unknown"


@dataclass
class CodeError:
    """A detected error stanza extracted from OCR text."""

    error_text: str
    surrounding_lines: list[str]
    file_hint: str = ""
    line_hint: str = ""
    pattern_kind: str = "unknown"  # "python_traceback", "ts_error", "generic", ...

    @property
    def fingerprint(self) -> str:
        h = hashlib.sha1(self.error_text.encode("utf-8")).hexdigest()[:12]
        return h

    def short_summary(self) -> str:
        first_line = self.error_text.splitlines()[0] if self.error_text else ""
        return first_line[:120]


@dataclass
class DebugSuggestion:
    """LLM-produced explanation + fix."""

    explanation: str
    fix_steps: list[str]
    code_patch: str = ""  # optional concrete patch
    confidence: float = 0.0

    def to_dict(self) -> dict:
        return {
            "explanation": self.explanation,
            "fix_steps": list(self.fix_steps),
            "code_patch": self.code_patch,
            "confidence": float(self.confidence),
        }


# ── IDE detection ────────────────────────────────────────────────────


# Patterns matched against the foreground window title (case-insensitive
# substring) to identify the IDE in use. Order matters — first match wins.
_IDE_TITLE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("visual studio code", "vscode"),
    ("cursor", "cursor"),
    ("vscodium", "vscode"),
    ("pycharm", "pycharm"),
    ("intellij idea", "intellij"),
    ("webstorm", "webstorm"),
    ("rider", "rider"),
    ("clion", "clion"),
    ("phpstorm", "phpstorm"),
    ("rubymine", "rubymine"),
    ("goland", "goland"),
    ("android studio", "android-studio"),
    ("xcode", "xcode"),
    ("sublime text", "sublime"),
    ("notepad++", "notepad++"),
    ("zed", "zed"),
    ("neovim", "neovim"),
    ("vim", "vim"),
)

# Window titles can be blank for newly-opened files (Cursor especially)
# or hidden behind generic strings, so we also classify by the IDE's
# process basename. Substring match against the lowercased process name.
_IDE_PROCESS_PATTERNS: tuple[tuple[str, str], ...] = (
    ("code.exe", "vscode"),
    ("code - insiders.exe", "vscode"),
    ("vscodium.exe", "vscode"),
    ("cursor.exe", "cursor"),
    ("pycharm", "pycharm"),    # pycharm64.exe / pycharm.exe
    ("idea", "intellij"),       # idea64.exe / idea.exe
    ("webstorm", "webstorm"),
    ("rider", "rider"),
    ("clion", "clion"),
    ("phpstorm", "phpstorm"),
    ("rubymine", "rubymine"),
    ("goland", "goland"),
    ("studio64.exe", "android-studio"),
    ("sublime_text.exe", "sublime"),
    ("notepad++.exe", "notepad++"),
    ("zed.exe", "zed"),
    ("nvim.exe", "neovim"),
)


class WindowProbe(Protocol):
    """Protocol the debugger uses to ask 'what window is foreground?'.

    Defaults to the activity-tracker probe; tests pass in a fake.
    """

    def snapshot(self) -> object:  # returns ForegroundSnapshot-ish
        ...


class IDEDetector:
    """Classifies the foreground window as a known IDE or 'unknown'."""

    def __init__(self, probe: WindowProbe | None = None):
        self._probe = probe

    def detect(self) -> IDEContext:
        snap = self._take_snapshot()
        if snap is None:
            return IDEContext(kind="unknown", title="", process_name="")
        title = getattr(snap, "title", "") or ""
        process = getattr(snap, "process_name", "") or ""
        kind = self.classify(title, process)
        return IDEContext(kind=kind, title=title, process_name=process)

    @staticmethod
    def classify(title: str, process_name: str = "") -> str:
        t = (title or "").lower()
        p = (process_name or "").lower()
        # Title patterns are checked first because they're more specific
        # (e.g. "PyCharm 2024.1") than the process basename.
        for needle, kind in _IDE_TITLE_PATTERNS:
            if needle in t:
                return kind
        # Then fall back to the process basename, which catches the case
        # where the IDE has just opened with no file (blank title).
        for needle, kind in _IDE_PROCESS_PATTERNS:
            if needle in p:
                return kind
        return "unknown"

    def _take_snapshot(self):
        if self._probe is not None:
            try:
                return self._probe.snapshot()
            except Exception:
                return None
        try:
            from core.utils.activity_tracker import ForegroundProbe
            return ForegroundProbe().snapshot()
        except Exception:
            return None


# ── Error stanza extraction ──────────────────────────────────────────


# Anchor patterns used to locate where an error stanza *starts* inside the
# OCR'd text. The order matters for two reasons:
#
#   1. Tie-break for ``pattern_kind`` when multiple anchors match the
#      same line — earlier entries win.
#   2. ``ts_error`` and ``js_error`` are listed BEFORE ``python_error``
#      because canonical-named JS errors (``TypeError``, ``ReferenceError``)
#      would otherwise be swallowed by the broad ``[A-Z][a-zA-Z]+Error``
#      Python anchor.
_ERROR_ANCHORS: tuple[tuple[str, str], ...] = (
    ("python_traceback", r"Traceback \(most recent call last\)"),
    ("ts_error",         r"error\s+TS\d{2,5}\b"),
    ("ts_error",         r"\bTSError\b"),
    ("js_error",         r"\b(ReferenceError|SyntaxError|TypeError|RangeError|EvalError)\b"),
    ("python_error",     r"\b([A-Z][a-zA-Z]+Error|[A-Z][a-zA-Z]+Exception)\b"),
    ("rust_error",       r"^error\[E\d+\]"),
    ("go_error",         r"\bcannot use\b|\bundefined: \b"),
    ("compile_error",    r"\b(error|Error):\s+"),
    ("npm_error",        r"\bnpm ERR!"),
    ("warning",          r"\b(warning|Warning):\s+"),
)


# Maximum number of lines we capture *after* the anchor before we
# truncate. Most real-world tracebacks fit comfortably in 25 lines.
_MAX_STANZA_LINES = 25
# Number of lines *above* the anchor we treat as code context. The LLM
# uses these to suggest a fix.
_CONTEXT_LINES_BEFORE = 8


def _looks_like_filename(line: str) -> tuple[str, str] | None:
    """Spot ``File "foo.py", line 42`` / ``foo.ts:23:14`` / similar.

    Returns ``(filename, line_number)`` or None.
    """
    m = re.search(r'File "([^"]+)", line (\d+)', line)
    if m:
        return m.group(1), m.group(2)
    m = re.search(r"([A-Za-z]:[\\\/][^:\s]+|\.{0,2}\/[^:\s]+|[\w./-]+\.\w{1,4}):(\d+)(?::(\d+))?", line)
    if m:
        return m.group(1), m.group(2)
    return None


def extract_error(ocr_text: str) -> Optional[CodeError]:
    """Pull the *latest* error stanza out of an OCR dump.

    If the OCR contains multiple errors, we take the last one (most
    recent on screen). Returns ``None`` if no anchor matches.
    """
    if not isinstance(ocr_text, str) or not ocr_text.strip():
        return None
    lines = ocr_text.splitlines()

    matches: list[tuple[int, str]] = []  # (line_index, pattern_kind)
    for kind, regex in _ERROR_ANCHORS:
        for i, line in enumerate(lines):
            if re.search(regex, line):
                matches.append((i, kind))

    if not matches:
        return None

    # If a Python traceback header is present, it always wins as the
    # ``pattern_kind`` and as the anchor line — the inner ``XError``
    # lines belong to the same stanza, not to a fresh JS-style error.
    traceback_lines = [li for li, k in matches if k == "python_traceback"]
    if traceback_lines:
        start_idx = max(traceback_lines)
        pattern_kind = "python_traceback"
    else:
        # No traceback context: fall back to "latest match wins, with the
        # more-specific kind breaking ties on the same line".
        kind_priority = {kind: idx for idx, (kind, _) in enumerate(_ERROR_ANCHORS)}
        matches.sort(key=lambda lk: (-lk[0], kind_priority.get(lk[1], 99)))
        start_idx, pattern_kind = matches[0]

    # Walk backwards to also capture continuation lines (indented under
    # ``Traceback`` blocks etc.) — we land on the actual anchor line and
    # collect a fixed window forward.
    anchor_line = start_idx
    end_idx = min(len(lines), anchor_line + _MAX_STANZA_LINES)
    error_lines = [ln for ln in lines[anchor_line:end_idx] if ln.strip() != ""]
    if not error_lines:
        return None

    error_text = "\n".join(error_lines)

    # Surrounding code context = the few lines above the anchor that
    # aren't blank and aren't themselves error lines.
    context_start = max(0, anchor_line - _CONTEXT_LINES_BEFORE)
    surrounding = [
        ln for ln in lines[context_start:anchor_line]
        if ln.strip() != ""
    ]

    # Try to spot a filename / line hint from the stanza itself.
    file_hint = ""
    line_hint = ""
    for ln in error_lines:
        hit = _looks_like_filename(ln)
        if hit is not None:
            file_hint, line_hint = hit
            break

    return CodeError(
        error_text=error_text.strip(),
        surrounding_lines=surrounding,
        file_hint=file_hint,
        line_hint=line_hint,
        pattern_kind=pattern_kind,
    )


# ── LLM prompt + parsing ─────────────────────────────────────────────


def build_debug_prompt(error: CodeError, ide: IDEContext) -> dict:
    """Build a system+user prompt asking the LLM to explain + fix."""
    system = (
        "You are an experienced developer pair-programming with the user. "
        "They have just pointed at an error on screen. Be concise, specific, "
        "and actionable. Hindi/Hinglish replies are welcome if the error "
        "context implies the user prefers it.\n\n"
        "Return ONLY a JSON object with these keys:\n"
        '  "explanation": one or two sentences saying WHAT went wrong\n'
        "                 and WHY in plain language.\n"
        '  "fix_steps": an array of 1-3 short imperative steps.\n'
        '  "code_patch": optional minimal corrected code (string), '
        '"" if a code change is not the fix.\n'
        '  "confidence": number between 0 and 1 reflecting how sure you '
        "are without seeing the full file.\n"
        "Do not include any prose outside the JSON object."
    )
    parts: list[str] = [
        f"IDE: {ide.kind} ({ide.title[:80]})",
        f"PATTERN_KIND: {error.pattern_kind}",
    ]
    if error.file_hint:
        parts.append(f"FILE_HINT: {error.file_hint}")
    if error.line_hint:
        parts.append(f"LINE_HINT: {error.line_hint}")
    parts.append("")
    parts.append("ERROR_STANZA:")
    parts.append(error.error_text)
    if error.surrounding_lines:
        parts.append("")
        parts.append("CODE_CONTEXT (the few lines above the error):")
        parts.extend(error.surrounding_lines)
    user = "\n".join(parts)
    return {"system": system, "user": user}


def parse_debug_response(raw: str) -> Optional[DebugSuggestion]:
    """Best-effort JSON extraction of the LLM's debug reply."""
    if not isinstance(raw, str) or not raw.strip():
        return None

    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].lstrip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return None
    import json
    try:
        d = json.loads(text[start: end + 1])
    except Exception:
        return None
    if not isinstance(d, dict):
        return None
    explanation = str(d.get("explanation", "")).strip()
    if not explanation:
        return None
    fix_steps = d.get("fix_steps") or []
    if not isinstance(fix_steps, list):
        fix_steps = [str(fix_steps)]
    fix_steps = [str(s).strip() for s in fix_steps if str(s).strip()]
    code_patch = str(d.get("code_patch", "") or "")
    try:
        confidence = float(d.get("confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    return DebugSuggestion(
        explanation=explanation,
        fix_steps=fix_steps,
        code_patch=code_patch,
        confidence=confidence,
    )


# ── Cache ────────────────────────────────────────────────────────────


@dataclass
class _CacheEntry:
    suggestion: DebugSuggestion
    created_at: float


class SuggestionCache:
    """Tiny TTL cache keyed by error fingerprint."""

    def __init__(self, ttl_s: float = 600.0, max_entries: int = 64):
        self.ttl_s = float(ttl_s)
        self.max_entries = int(max_entries)
        self._entries: dict[str, _CacheEntry] = {}

    def get(self, fingerprint: str, now: float) -> Optional[DebugSuggestion]:
        entry = self._entries.get(fingerprint)
        if entry is None:
            return None
        if (now - entry.created_at) > self.ttl_s:
            self._entries.pop(fingerprint, None)
            return None
        return entry.suggestion

    def put(self, fingerprint: str, suggestion: DebugSuggestion, now: float) -> None:
        if len(self._entries) >= self.max_entries:
            # Evict the oldest entry (poor man's LRU).
            oldest = min(self._entries.items(), key=lambda kv: kv[1].created_at)
            self._entries.pop(oldest[0], None)
        self._entries[fingerprint] = _CacheEntry(suggestion=suggestion, created_at=now)


# ── Engine ───────────────────────────────────────────────────────────


# The OCR caller signature: it must produce a raw text dump of whatever
# is currently on screen (or in the IDE region). We let the caller pick
# the strategy (RapidOCR / Tesseract / synthetic fixture in tests).
OCRCallable = Callable[[], str]
LLMCaller = Callable[[dict], str]


@dataclass
class DebugResult:
    ide: IDEContext
    error: Optional[CodeError]
    suggestion: Optional[DebugSuggestion]
    from_cache: bool = False
    skipped_reason: str = ""


class CodeDebugger:
    """Public facade. ``run_once`` is what the executor calls."""

    def __init__(
        self,
        ide_detector: IDEDetector | None = None,
        ocr_caller: OCRCallable | None = None,
        llm_caller: LLMCaller | None = None,
        cache: SuggestionCache | None = None,
        clock: Callable[[], float] = time.time,
    ):
        self.ide_detector = ide_detector or IDEDetector()
        self.ocr_caller = ocr_caller
        self.llm_caller = llm_caller
        self.cache = cache or SuggestionCache()
        self.clock = clock

    def run_once(self) -> DebugResult:
        ide = self.ide_detector.detect()
        if not ide.is_known():
            logger.logger.info(
                f"CodeDebugger: foreground is not a known IDE "
                f"('{ide.title[:40]}'), skipping"
            )
            return DebugResult(
                ide=ide, error=None, suggestion=None,
                skipped_reason="not_an_ide",
            )

        ocr = self._resolve_ocr()
        if ocr is None:
            return DebugResult(
                ide=ide, error=None, suggestion=None,
                skipped_reason="ocr_unavailable",
            )
        try:
            text = ocr() or ""
        except Exception as e:
            logger.logger.warning(f"CodeDebugger: OCR failed: {e}")
            return DebugResult(
                ide=ide, error=None, suggestion=None,
                skipped_reason=f"ocr_error: {e!r}",
            )

        error = extract_error(text)
        if error is None:
            return DebugResult(
                ide=ide, error=None, suggestion=None,
                skipped_reason="no_error_in_view",
            )

        cached = self.cache.get(error.fingerprint, now=self.clock())
        if cached is not None:
            return DebugResult(
                ide=ide, error=error, suggestion=cached, from_cache=True,
            )

        llm = self._resolve_llm()
        if llm is None:
            return DebugResult(
                ide=ide, error=error, suggestion=None,
                skipped_reason="llm_unavailable",
            )

        prompt = build_debug_prompt(error, ide)
        try:
            raw = llm(prompt)
        except Exception as e:
            logger.logger.warning(f"CodeDebugger: LLM call failed: {e}")
            return DebugResult(
                ide=ide, error=error, suggestion=None,
                skipped_reason=f"llm_error: {e!r}",
            )

        suggestion = parse_debug_response(raw or "")
        if suggestion is None:
            return DebugResult(
                ide=ide, error=error, suggestion=None,
                skipped_reason="llm_unparseable",
            )

        self.cache.put(error.fingerprint, suggestion, now=self.clock())
        logger.logger.info(
            f"CodeDebugger: suggestion ready for "
            f"'{error.short_summary()[:60]}' (confidence={suggestion.confidence:.2f})"
        )
        return DebugResult(ide=ide, error=error, suggestion=suggestion)

    # ── Resolvers ────────────────────────────────────────────────────

    def _resolve_ocr(self) -> Optional[OCRCallable]:
        if self.ocr_caller is not None:
            return self.ocr_caller
        try:
            from core.ocr.engine import ocr_engine

            def _call() -> str:
                # Capture the whole screen and OCR — heavy but reliable.
                try:
                    import mss
                    from PIL import Image
                except Exception as e:
                    raise RuntimeError(f"screen capture unavailable: {e}")
                with mss.mss() as sct:
                    raw = sct.grab(sct.monitors[0])
                    img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
                return ocr_engine.recognize(img) or ""

            return _call
        except Exception as e:
            logger.logger.warning(f"CodeDebugger: default OCR wiring failed: {e}")
            return None

    def _resolve_llm(self) -> Optional[LLMCaller]:
        if self.llm_caller is not None:
            return self.llm_caller
        try:
            from core.engine.llm_bridge import LLMBridge
            bridge = LLMBridge()

            def _call(prompt: dict) -> str:
                return bridge.generate_text(
                    system_prompt=prompt["system"],
                    user_prompt=prompt["user"],
                ) or ""

            return _call
        except Exception as e:
            logger.logger.warning(f"CodeDebugger: default LLM wiring failed: {e}")
            return None


# Module-level singleton.
code_debugger = CodeDebugger()
