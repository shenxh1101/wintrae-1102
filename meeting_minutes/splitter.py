from __future__ import annotations

import re
from typing import List, Tuple

from .models import SpeakerSegment

SPEAKER_PATTERNS = [
    re.compile(r"^([\u4e00-\u9fff]{2,4}|[A-Za-z]+(?:\s[A-Za-z]+)*)\s*[：:]\s*", re.MULTILINE),
    re.compile(r"^【([^】]{1,10})】\s*[：:]?\s*", re.MULTILINE),
    re.compile(r"^\[([^\]]{1,10})\]\s*[：:]?\s*", re.MULTILINE),
    re.compile(r"^((?:发言|说话|讲)人\s*[\d一二三四五六七八九十]+)\s*[：:.\s]\s*", re.MULTILINE),
    re.compile(r"^((?:嘉宾|主持|与会|列席)人\s*[\d一二三四五六七八九十]?)\s*[：:.\s]\s*", re.MULTILINE),
]

TIMESTAMP_PATTERNS = [
    re.compile(r"\[(\d{1,2}:\d{2}(?::\d{2})?)\]"),
    re.compile(r"<(\d{1,2}:\d{2}(?::\d{2})?)>"),
    re.compile(r"（(\d{1,2}:\d{2}(?::\d{2})?)）"),
]

SPEAKER_NORMALIZATION_MAP = {
    "发言人1": "发言人1",
    "发言人2": "发言人2",
    "发言人3": "发言人3",
    "发言人4": "发言人4",
    "发言人5": "发言人5",
    "嘉宾1": "嘉宾1",
    "嘉宾2": "嘉宾2",
    "主持人1": "主持人",
    "主持人": "主持人",
    "主讲人": "主讲人",
}


def split_by_speakers(text: str) -> List[SpeakerSegment]:
    if not text.strip():
        return []

    combined = _combine_patterns()
    matches = list(combined.finditer(text))

    if not matches:
        return _split_by_paragraphs(text)

    segments = []
    for i, match in enumerate(matches):
        speaker = _get_speaker_from_match(match)
        speaker = _normalize_speaker(speaker)
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        content = re.sub(r"^[：:]\s*", "", content)
        timestamp, content = _extract_timestamp(content)

        if content:
            segments.append(SpeakerSegment(
                speaker=speaker,
                content=content,
                timestamp=timestamp,
            ))

    segments = _merge_consecutive_same_speaker(segments)
    return segments


def _combine_patterns() -> re.Pattern:
    alternatives = []
    for p in SPEAKER_PATTERNS:
        alternatives.append(p.pattern)
    combined_str = "|".join(alternatives)
    combined = re.compile(combined_str, re.MULTILINE)
    return combined


def _get_speaker_from_match(match: re.Match) -> str:
    for i in range(1, len(match.groups()) + 1):
        val = match.group(i)
        if val is not None:
            return val.strip()
    return "未知发言人"


def _normalize_speaker(speaker: str) -> str:
    s = speaker.strip()
    if s in SPEAKER_NORMALIZATION_MAP:
        return SPEAKER_NORMALIZATION_MAP[s]

    s = re.sub(r"^[【\[\(（](.*?)[】\]\)）]$", r"\1", s)
    s = re.sub(r"[【\[\(【\】\]\)）]", "", s)

    if re.match(r"^(?:发言|说话|讲|嘉)人\s*[\d一二三四五六七八九十]+", s):
        return s

    s = s.strip()
    if len(s) >= 2:
        return s
    return speaker


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
    for pattern in TIMESTAMP_PATTERNS:
        match = pattern.match(text)
        if match:
            ts = match.group(1)
            rest = text[match.end():].strip()
            return ts, rest
    return "", text


def _merge_consecutive_same_speaker(segments: List[SpeakerSegment]) -> List[SpeakerSegment]:
    if not segments:
        return []

    merged = [SpeakerSegment(
        speaker=segments[0].speaker,
        content=segments[0].content,
        timestamp=segments[0].timestamp,
    )]

    for seg in segments[1:]:
        if merged and seg.speaker == merged[-1].speaker:
            merged[-1].content += " " + seg.content
            if seg.timestamp and not merged[-1].timestamp:
                merged[-1].timestamp = seg.timestamp
        else:
            merged.append(SpeakerSegment(
                speaker=seg.speaker,
                content=seg.content,
                timestamp=seg.timestamp,
            ))

    return merged


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
