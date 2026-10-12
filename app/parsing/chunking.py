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
        if estimate_tokens(joined) > target:
            words = joined.split()
            step = max(1, target - overlap)
            for offset in range(0, len(words), step):
                piece = " ".join(words[offset : offset + target])
                if not piece:
                    break
                chunks.append(Chunk(len(chunks), piece, _location_for(current_start, locations)))
                if offset + target >= len(words):
                    break
        else:
            chunks.append(Chunk(ordinal, joined, _location_for(current_start, locations)))
        ordinal = len(chunks)
        tail = joined.split()[-overlap:] if overlap else []
        current, current_start = ([" ".join(tail)] if tail else []), current_start

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
