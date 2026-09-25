"""Fenix identity guard — hard server-side guarantee of one public identity.

Every brain in the private Fenix chain is instructed to present itself only as
**Fenix Core LoRA**. Instructions are strong, but a model can still slip. This
module is the last line of defense: user-facing text is scrubbed of any
provider or model name before it leaves the server.

Scope rules:
- Prose is scrubbed (chat answers, lyrics, audio prompts, statuses).
- Fenced code blocks (``` ... ```) and inline code are preserved verbatim:
  technical answers must stay correct even when the user is literally building
  a Gemini client.
- Replacement is identity-consistent: any engine mention becomes the Fenix
  identity, attribution becomes Hakari.
"""
from __future__ import annotations

import re

# (pattern, replacement) — applied to prose only, in order.
_REPLACEMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Google's Gemini / Google Gemini / bare Gemini
    (re.compile(r"google['’`]?\s*gemini", re.I), "Fenix Core LoRA"),
    (re.compile(r"\bgemini\b", re.I), "Fenix Core LoRA"),
    # Free-layer model families (Qwen / Llama / GPT-oss / DeepSeek)
    (re.compile(r"\bqwen[a-z0-9.\-/]*", re.I), "fenix-core-lora"),
    (re.compile(r"\bllama-?[a-z0-9.\-/]*", re.I), "fenix-core-lora"),
    (re.compile(r"\bgpt-oss-[a-z0-9\-]*", re.I), "fenix-core-lora"),
    (re.compile(r"\bdeepseek[a-z0-9\-]*", re.I), "fenix-core-lora"),
    # Provider brands
    (re.compile(r"\bgroq\b|\bcerebras\b|\bopenrouter\b|\bserper\b", re.I), "Fenix Core"),
    (re.compile(r"\bhugging\s*face\b", re.I), "Fenix compute"),
    (re.compile(r"\bmodal\b", re.I), "Fenix"),
    # Attribution: the builder is Hakari, not a third party
    (re.compile(r"من\s+(?:طرف\s+)?جوجل|من\s+Google|بواسطة\s+Google", re.I), "من قبل Hakari"),
    (re.compile(r"\bby\s+Google\b|\bfrom\s+Google\b", re.I), "by Hakari"),
)

# Cleanups after replacement (order matters)
_CLEANUPS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Version leftovers after the identity: "Fenix Core LoRA 3.5 Flash" -> "Fenix Core LoRA"
    (re.compile(r"Fenix Core LoRA(?:\s+[0-9][\w.\-]*(?:\s+(?:flash|pro|lite|ultra|nano|instant|mini|preview|latest))*)+", re.I), "Fenix Core LoRA"),
    # Duplicated attribution: "by Hakari by Hakari" -> "by Hakari"
    (re.compile(r"(by Hakari)(?:\s+by Hakari)+", re.I), r"\1"),
    (re.compile(r"(من قبل Hakari)(?:\s+من قبل Hakari)+", re.I), r"\1"),
)

_FENCE = re.compile(r"```")
_INLINE_CODE = re.compile(r"`[^`\n]+`")


def _scrub(text: str) -> str:
    for pattern, replacement in _REPLACEMENTS:
        text = pattern.sub(replacement, text)
    for pattern, replacement in _CLEANUPS:
        text = pattern.sub(replacement, text)
    return text


def _merge_spans(spans: list[tuple[int, int]]) -> list[list[int]]:
    merged: list[list[int]] = []
    for s, e in sorted(spans):
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return merged


def _preserved_spans(text: str) -> list[list[int]]:
    """Spans to keep verbatim: whole fenced blocks + inline code."""
    spans: list[tuple[int, int]] = []
    fences = list(_FENCE.finditer(text))
    i = 0
    while i + 1 < len(fences):
        # A complete fenced block: opening fence through closing fence.
        spans.append((fences[i].start(), fences[i + 1].end()))
        i += 2
    if len(fences) % 2 == 1:
        # Unclosed fence (partial stream): keep from the last fence to the end.
        spans.append((fences[-1].start(), len(text)))
    for m in _INLINE_CODE.finditer(text):
        # Skip inline spans already inside fenced blocks — merge handles it.
        spans.append((m.start(), m.end()))
    return _merge_spans(spans)


def sanitize_reply(text: str) -> str:
    """Scrub provider names from a complete reply, preserving code spans."""
    if not text:
        return text
    out: list[str] = []
    pos = 0
    for s, e in _preserved_spans(text):
        out.append(_scrub(text[pos:s]))
        out.append(text[s:e])
        pos = e
    out.append(_scrub(text[pos:]))
    return "".join(out)


def split_sentences(buffer: str) -> tuple[str, str]:
    """Return (complete-sentence prefix, remainder) for stream buffering.

    Streaming scrubbing must never cut a provider name in half between
    deltas, so text is flushed only at sentence boundaries.
    """
    m = re.match(r"^(.*[.!?؟\n])", buffer, re.S)
    if m:
        return m.group(1), buffer[m.end():]
    return "", buffer


def make_stream_scrubber() -> "object":
    """Stateful scrubber for streamed, sentence-flushed text.

    Call ``scrub(chunk)`` on each sentence-sized flush of accumulated stream
    text. Prose is scrubbed; fenced code passes through untouched, with fence
    state tracked correctly across flush boundaries. Finish with a final flush
    that ends in a space so the tail is processed, then rely on
    ``finalize()`` for any remainder.
    """
    state = {"in_fence": False}

    def scrub(chunk: str) -> str:
        out: list[str] = []
        pos = 0
        for m in _FENCE.finditer(chunk):
            if state["in_fence"]:
                out.append(chunk[pos:m.end()])  # closing fence + code tail stay raw
                state["in_fence"] = False
            else:
                out.append(_scrub(chunk[pos:m.start()]))
                out.append("```")
                state["in_fence"] = True
            pos = m.end()
        out.append(chunk[pos:] if state["in_fence"] else _scrub(chunk[pos:]))
        return "".join(out)

    def finalize(tail: str) -> str:
        # Tail text may still open a fence; a trailing open fence stays raw.
        return scrub(tail)

    scrub.finalize = finalize  # type: ignore[attr-defined]
    return scrub
