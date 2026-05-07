"""Claude-backed diagnosis for failed (or merely puzzling) conversions (Issue #36).

This module is pure logic: no FastAPI imports, no DB session. The route
layer in routes/diagnosis.py handles persistence and access control;
this module assembles the prompt context, calls Claude, and returns the
text + token usage.

We use Sonnet 4.6 (named in the issue) with adaptive thinking and
prompt caching on the system block, so follow-up turns stay cheap.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from .models import Manuscript
from .storage import Storage

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 2048

# Hard caps so a single call can't blow past the issue's budget.
_MAX_LOG_LINES = 500
_MAX_PER_FILE_CHARS = 100_000
_MAX_TOTAL_SOURCE_CHARS = 200_000
# Text files in the source tree we ship to Claude. Includes .bib (the
# bibliography source — distinct from the .bbl latex generated artifact),
# .cls / .sty (in case the journal class file is local or patched), and
# Quarto's .qmd / .yml config alongside .tex.
_SOURCE_EXTENSIONS = {
    ".tex", ".bib", ".bbl", ".cls", ".sty", ".qmd", ".yml", ".yaml",
}


SYSTEM_PROMPT = """You are diagnosing problems with a LaTeX or Quarto journal article \
that an academic author has submitted to the AUP Online publishing platform.

The pipeline runs `latexmlc` (LaTeXML), then `latexmlpost`, then a chain of \
Python post-processing fixups, to convert the source into JATS XML. Each step \
emits warnings and errors. Common failure modes include unclosed environments, \
missing labels, broken bibliography entries (.bib syntax / unmatched citation \
keys), unsupported macros, and figures that produce no `<graphic>`.

Your job is to read the failure context the user supplies and explain, in \
plain language, what is wrong with the *source* and what the author should \
change. Be concrete: name the specific file, the macro or environment to fix, \
and where possible quote the offending line.

Important framing:

- You are giving an educated guess. Always remind the author at the end that \
  this is Claude's interpretation and they should verify before changing the \
  source.
- Do not invent line numbers, file paths, or content you can't see.
- If the logs don't clearly point at a cause, say so honestly and suggest \
  what additional context (e.g. the surrounding paragraph) would help.
- Keep responses tight: a short summary, then concrete suggestions. Skip \
  preamble like "I'll analyze this for you".
- Authors are often non-technical. Explain LaTeX concepts when relevant."""


@dataclass
class AssistantTurn:
    content: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int


def _tail_lines(text: str, n: int) -> str:
    if not text:
        return ""
    lines = text.splitlines()
    if len(lines) <= n:
        return text
    return "\n".join(["[... earlier lines truncated ...]", *lines[-n:]])


def _read_capped(path: Path, max_chars: int) -> str | None:
    try:
        data = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeError):
        return None
    if len(data) > max_chars:
        return data[:max_chars] + f"\n[... {len(data) - max_chars} chars truncated ...]"
    return data


def _failed_step_logs(ms: Manuscript) -> str:
    """Concatenate the logs of any non-OK pipeline step."""
    steps = ms.pipeline_steps or []
    chunks: list[str] = []
    for step in steps:
        # pipeline_steps is a list of dicts coming back from JSON storage.
        status = step.get("status") if isinstance(step, dict) else None
        if status in (None, "ok", "skipped", "pending"):
            continue
        name = step.get("name", "?")
        chunks.append(f"## Step: {name} (status={status})\n")
        for log in step.get("logs", []) or []:
            log_name = log.get("name", "log")
            content = _tail_lines(log.get("content", "") or "", _MAX_LOG_LINES)
            chunks.append(f"### {log_name}\n{content}\n")
    return "\n".join(chunks).strip()


def _collect_source_files(
    source_dir: Path, main_file: str | None
) -> list[tuple[str, str]]:
    """Bundle every text source file in ``source_dir`` for the prompt.

    Returns ``(relative_path, content)`` pairs. The detected main file
    comes first so it dominates Claude's attention; everything else
    follows in deterministic alphabetical order so the prompt cache hits
    on repeat calls. Each file is capped at ``_MAX_PER_FILE_CHARS`` and
    the cumulative total at ``_MAX_TOTAL_SOURCE_CHARS``; further files
    are listed by name only with a "(omitted, budget reached)" marker so
    Claude knows they exist.
    """
    candidates: list[Path] = []
    for path in sorted(source_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in _SOURCE_EXTENSIONS:
            continue
        candidates.append(path)

    main = _detect_main_source(source_dir, main_file)
    if main is not None and main in candidates:
        candidates.remove(main)
        candidates.insert(0, main)

    out: list[tuple[str, str]] = []
    used = 0
    for path in candidates:
        rel = path.relative_to(source_dir).as_posix()
        if used >= _MAX_TOTAL_SOURCE_CHARS:
            out.append((rel, "(omitted, source-context budget reached)"))
            continue
        content = _read_capped(path, _MAX_PER_FILE_CHARS)
        if content is None:
            continue
        out.append((rel, content))
        used += len(content)
    return out


def _detect_main_source(source_dir: Path, main_file: str | None) -> Path | None:
    if main_file:
        candidate = source_dir / main_file
        if candidate.is_file():
            return candidate
    for name in ("main.tex", "main.qmd"):
        candidate = source_dir / name
        if candidate.is_file():
            return candidate
    # First .tex / .qmd we find as a fallback.
    for ext in ("*.tex", "*.qmd"):
        matches = sorted(source_dir.glob(ext))
        if matches:
            return matches[0]
    return None


def build_failure_context(
    ms: Manuscript, storage: Storage, *, include_source: bool = True
) -> str:
    """Assemble the first user-message blob for a fresh chat.

    ``include_source`` ships every text file in ``source/`` (capped per
    file and overall — see _MAX_PER_FILE_CHARS / _MAX_TOTAL_SOURCE_CHARS).
    Set it false to send only the pipeline logs — useful when the author
    wants to keep the prompt small or doesn't want to share their full
    source.
    """
    parts: list[str] = []
    parts.append(
        f"Manuscript: {ms.doi_suffix}\n"
        f"Status: {ms.status}\n"
        f"Title: {ms.title or '(none)'}"
    )

    step_logs = _failed_step_logs(ms)
    if step_logs:
        parts.append("# Pipeline step output\n\n" + step_logs)
    elif ms.job_log:
        parts.append(
            "# Aggregated job log\n\n" + _tail_lines(ms.job_log, _MAX_LOG_LINES)
        )
    else:
        parts.append(
            "# Pipeline output\n\nNo per-step logs are recorded for this "
            "manuscript. The author may be asking about output formatting "
            "rather than a hard failure."
        )

    if include_source:
        source_dir = storage.source_dir(ms.doi_suffix)
        if source_dir.is_dir():
            for label, content in _collect_source_files(source_dir, ms.main_file):
                parts.append(f"# Source: {label}\n\n```\n{content}\n```")

    parts.append(
        "Please diagnose what (if anything) is wrong, in plain language for "
        "the author. End with a one-line reminder that this is your guess and "
        "they should verify."
    )

    return "\n\n".join(parts)


def call_claude(messages: list[dict]) -> AssistantTurn:
    """Call Sonnet 4.6 with prompt caching.

    Two cache breakpoints — on the system prompt (shared across every
    manuscript) and on the most recent message (caches the full
    conversation prefix per-manuscript). The first turn pays for ~50k
    input tokens of source bundle; every follow-up reads that prefix
    back at ~10% the price.

    ``messages`` is a list of ``{"role": ..., "content": ...}`` dicts in
    Anthropic's wire format (i.e. only role/content — no timestamps or
    usage fields).
    """
    # Imported lazily so the rest of the app loads without `anthropic`
    # installed (e.g. before `uv sync --extra web`).
    import anthropic

    api_messages: list[dict] = list(messages[:-1])
    last = messages[-1]
    api_messages.append(
        {
            "role": last["role"],
            "content": [
                {
                    "type": "text",
                    "text": last["content"],
                    "cache_control": {"type": "ephemeral"},
                }
            ],
        }
    )

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=api_messages,
    )
    text = "".join(b.text for b in response.content if b.type == "text")
    return AssistantTurn(
        content=text,
        input_tokens=response.usage.input_tokens or 0,
        output_tokens=response.usage.output_tokens or 0,
        cache_read_tokens=getattr(response.usage, "cache_read_input_tokens", 0) or 0,
    )


def is_enabled() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))
