from __future__ import annotations

import re
from typing import List, Optional, Tuple

from .models import SpeakerSegment

SPEAKER_PATTERNS = [
    re.compile(r"^((?:[\u4e00-\u9fff]{2,4}|[A-Za-z]+(?:\s[A-Za-z]+)*))\s*[：:]\s*", re.MULTILINE),
    re.compile(r"^【([^】]+)】\s*", re.MULTILINE),
    re.compile(r"^\[([^\]]+)\]\s*", re.MULTILINE),
    re.compile(r"^((?:发言|说话|讲)人\s*[\d一二三四五六七八九十]+)\s*[：:.\s]\s*", re.MULTILINE),
]

TIMESTAMP_PATTERN = re.compile(r"\[(\d{1,2}:\d{2}(?::\d{2})?)\]")


def split_by_speakers(text: str) -> List[SpeakerSegment]:
    if not text.strip():
        return []

    combined = _combine_patterns()

    matches = list(combined.finditer(text))
    if not matches:
        return _split_by_paragraphs(text)

    segments = []
    for i, match in enumerate(matches):
        speaker = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        timestamp, content = _extract_timestamp(content)

        if content:
            segments.append(SpeakerSegment(
                speaker=speaker,
                content=content,
                timestamp=timestamp,
            ))

    return segments


def _combine_patterns() -> re.Pattern:
    parts = []
    for p in SPEAKER_PATTERNS:
        inner = p.pattern.lstrip("^").rstrip(r"\s*")
        parts.append(f"(?:{inner})")

    combined = re.compile(
        rf"^((?:[\u4e00-\u9fff]{{2,4}}|[A-Za-z]+(?:\s[A-Za-z]+)*))\s*[：:]\s*",
        re.MULTILINE,
    )
    return combined


def _split_by_paragraphs(text: str) -> List[SpeakerSegment]:
    paragraphs = re.split(r"\n\s*\n", text)
    segments = []
    for i, para in enumerate(paragraphs):
        para = para.strip()
        if not para:
            continue
        timestamp, para = _extract_timestamp(para)
        if para:
            segments.append(SpeakerSegment(
                speaker=f"发言人{i + 1}",
                content=para,
                timestamp=timestamp,
            ))
    return segments


def _extract_timestamp(text: str) -> Tuple[str, str]:
    match = TIMESTAMP_PATTERN.match(text)
    if match:
        ts = match.group(1)
        rest = text[match.end():].strip()
        return ts, rest
    return "", text


def merge_short_segments(segments: List[SpeakerSegment], min_length: int = 10) -> List[SpeakerSegment]:
    if not segments:
        return []

    merged = [SpeakerSegment(
        speaker=segments[0].speaker,
        content=segments[0].content,
        timestamp=segments[0].timestamp,
    )]

    for seg in segments[1:]:
        if len(seg.content) < min_length and merged:
            merged[-1].content += " " + seg.content
        else:
            merged.append(SpeakerSegment(
                speaker=seg.speaker,
                content=seg.content,
                timestamp=seg.timestamp,
            ))

    return merged
