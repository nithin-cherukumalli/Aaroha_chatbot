from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain import SourceLocation


@dataclass(frozen=True)
class Chunk:
    ordinal: int
    text: str
    location: SourceLocation


def estimate_tokens(text: str) -> int:
    """Conservative fallback tokenizer: used only for deterministic bound checks.

    Production activation requires the configured tokenizer to be reviewed; this estimate
    intentionally counts punctuation separately and does not download model weights.
    """
    return len(re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE))


def _location_for(offset: int, locations: list[tuple[int, int, SourceLocation]]) -> SourceLocation:
    for begin, end, location in locations:
        if begin <= offset < end:
            return location
    return locations[-1][2] if locations else SourceLocation(section="document")


def chunk_text(
    text: str, locations: list[tuple[int, int, SourceLocation]], target: int, overlap: int
) -> list[Chunk]:
    paragraphs = [
        (match.start(), match.group().strip())
        for match in re.finditer(r"[^\n]+(?:\n(?!\n)[^\n]+)*", text)
    ]
    chunks, current, current_start, ordinal = [], [], 0, 0

    def flush() -> None:
        nonlocal current, current_start, ordinal
        if not current:
            return
        joined = "\n\n".join(current)
        loc = _location_for(current_start, locations)
        if estimate_tokens(joined) > target:
            words = joined.split()
            i = 0
            while i < len(words):
                j = i + 1
                while j <= len(words) and estimate_tokens(" ".join(words[i:j])) <= target:
                    j += 1
                chunk_words = words[i : max(i + 1, j - 1)]
                chunks.append(Chunk(len(chunks), " ".join(chunk_words), loc))
                consumed = len(chunk_words)
                if i + consumed >= len(words):
                    break
                backtrack = i + consumed - 1
                while backtrack > i and estimate_tokens(" ".join(words[backtrack : i + consumed])) <= overlap:
                    backtrack -= 1
                i = max(i + 1, backtrack + 1)

            tail_start = len(words) - 1
            while tail_start >= 0 and estimate_tokens(" ".join(words[tail_start:])) <= overlap:
                tail_start -= 1
            tail = words[tail_start + 1:] if overlap else []
            current, current_start = ([" ".join(tail)] if tail else []), current_start
        else:
            chunks.append(Chunk(len(chunks), joined, loc))
            tail = joined.split()[-overlap:] if overlap else []
            while tail and estimate_tokens(" ".join(tail)) > overlap:
                tail.pop(0)
            current, current_start = ([" ".join(tail)] if tail else []), current_start
        ordinal = len(chunks)

    for start, paragraph in paragraphs:
        if not current:
            current_start = start
        candidate = "\n\n".join([*current, paragraph])
        if current and estimate_tokens(candidate) > target:
            flush()
            current_start = start
        current.append(paragraph)
    flush()
    return chunks
