from __future__ import annotations

import re
from typing import List

FILLER_WORDS = [
    r"嗯[，,]?",
    r"啊[，,]?",
    r"呃[，,]?",
    r"额[，,]?",
    r"那个[，,]?",
    r"就是说[，,]?",
    r"然后呢[，,]?",
    r"对吧[，,]?",
    r"对对对[，,]?",
    r"是吧[，,]?",
    r"嗯嗯[，,]?",
    r"好的好的[，,]?",
    r"就是嘛[，,]?",
    r"你知道吗[，,]?",
    r"怎么说呢[，,]?",
    r"的话[，,]?",
    r"什么的[，,]?",
    r"之类的[，,]?",
]

DUPLICATE_PATTERNS = [
    (r"(对[，,]?){3,}", "对"),
    (r"(嗯[，,]?){3,}", "嗯"),
    (r"(好[，,]?){3,}", "好"),
    (r"(是[，,]?){3,}", "是"),
]

SENTENCE_END_PATTERNS = [
    (r"([。！？])\1+", r"\1"),
]

FILLER_COMPILED = [re.compile(p) for p in FILLER_WORDS]
DUPLICATE_COMPILED = [(re.compile(p), r) for p, r in DUPLICATE_PATTERNS]
SENTENCE_END_COMPILED = [(re.compile(p), r) for p, r in SENTENCE_END_PATTERNS]

WHITESPACE_PATTERN = re.compile(r"\s+")


def clean_text(text: str, custom_fillers: List[str] | None = None) -> str:
    if not text.strip():
        return ""

    patterns = list(FILLER_COMPILED)
    if custom_fillers:
        patterns.extend(re.compile(p) for p in custom_fillers)

    result = text
    for p in patterns:
        result = p.sub("", result)

    for p, r in DUPLICATE_COMPILED:
        result = p.sub(r, result)

    for p, r in SENTENCE_END_COMPILED:
        result = p.sub(r, result)

    result = WHITESPACE_PATTERN.sub(" ", result)

    result = re.sub(r"[，,]{2,}", "，", result)
    result = re.sub(r"^[，,。\s]+", "", result)
    result = re.sub(r"[，,。\s]+$", "", result)

    return result.strip()


def clean_segments(segments: list, custom_fillers: List[str] | None = None) -> list:
    from .models import SpeakerSegment

    cleaned = []
    for seg in segments:
        cleaned_content = clean_text(seg.content, custom_fillers)
        if cleaned_content:
            cleaned.append(SpeakerSegment(
                speaker=seg.speaker,
                content=cleaned_content,
                timestamp=seg.timestamp,
            ))
    return cleaned
