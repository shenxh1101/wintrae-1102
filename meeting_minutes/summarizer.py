from __future__ import annotations

import re
from typing import List, Optional

from .models import AgendaItem, SpeakerSegment

AGENDA_TITLE_PATTERNS = [
    re.compile(r"(?:议题|主题|话题|讨论项|事项)[一二三四五六七八九十\d]*[、.:：\s]+(.+?)(?:[。\n]|$)"),
    re.compile(r"(?:第[一二三四五六七八九十\d]+[个项])\s*(.+?)(?:[。，；\n]|$)"),
    re.compile(r"(\d+)[、.．]\s*(.{2,30}?)(?:[。\n]|$)"),
    re.compile(r"^[一二三四五六七八九十]+[、.．]\s*(.{2,30}?)(?:[。\n]|$)", re.MULTILINE),
]

KEY_SENTENCE_PATTERNS = [
    re.compile(r"(?:重点|关键|核心|重要|务必|必须|一定要|需要注意的是?|值得注意的是)\s*[的是：:]?\s*(.+?)(?:[。\n]|$)"),
    re.compile(r"(?:结论|决定|确认|明确|同意|一致认为)\s*[的是：:]?\s*(.+?)(?:[。\n]|$)"),
]

RISK_PATTERNS = [
    re.compile(r"(?:风险|隐患|问题|担心|担忧|困难|挑战|障碍|阻碍)\s*[的是有：:]?\s*(.+?)(?:[。\n]|$)"),
    re.compile(r"(?:可能导致|可能会|有可能|恐将|恐怕)\s*(.+?)(?:[。\n]|$)"),
    re.compile(r"(?:如果不?及时|若不?及时|一旦|如果.+?则)\s*(.+?)(?:[。\n]|$)"),
]

HIGHLIGHT_PATTERNS = [
    re.compile(r"(?:重点|关键|核心|重要|务必|必须|一定要)\s*[的是：:]?\s*.+?[。]"),
    re.compile(r"(?:结论|决定|确认|明确|同意|一致认为)\s*[的是：:]?\s*.+?[。]"),
]


def extract_agendas(segments: List[SpeakerSegment], raw_text: str = "") -> List[AgendaItem]:
    text = raw_text
    if not text and segments:
        text = "\n".join(f"{s.speaker}：{s.content}" for s in segments)

    if not text:
        return []

    titles = _extract_agenda_titles(text)
    key_sentences = _extract_key_sentences(text)
    risks = _extract_risks(text)

    if not titles:
        return [_build_single_agenda(text, key_sentences, risks)]

    agendas = []
    sections = _split_by_agendas(text, titles)

    for i, title in enumerate(titles):
        section_text = sections[i] if i < len(sections) else ""
        section_keys = _extract_key_sentences(section_text) if section_text else []
        section_risks = _extract_risks(section_text) if section_text else []

        agendas.append(AgendaItem(
            title=title.strip(),
            content=section_text.strip()[:500],
            key_sentences=section_keys,
            risks=section_risks,
        ))

    remaining_keys = [k for k in key_sentences if not any(k in a.key_sentences for a in agendas)]
    remaining_risks = [r for r in risks if not any(r in a.risks for a in agendas)]
    if remaining_keys and agendas:
        agendas[-1].key_sentences.extend(remaining_keys)
    if remaining_risks and agendas:
        agendas[-1].risks.extend(remaining_risks)

    return agendas


def extract_highlights(segments: List[SpeakerSegment], raw_text: str = "") -> List[str]:
    text = raw_text
    if not text and segments:
        text = "\n".join(f"{s.speaker}：{s.content}" for s in segments)

    if not text:
        return []

    highlights = []
    for pattern in HIGHLIGHT_PATTERNS:
        for match in pattern.finditer(text):
            h = match.group(0).strip()
            if h and h not in highlights:
                highlights.append(h)

    return highlights


def extract_risks(segments: List[SpeakerSegment], raw_text: str = "") -> List[str]:
    text = raw_text
    if not text and segments:
        text = "\n".join(f"{s.speaker}：{s.content}" for s in segments)

    return _extract_risks(text) if text else []


def _extract_agenda_titles(text: str) -> List[str]:
    titles = []
    seen = set()
    for pattern in AGENDA_TITLE_PATTERNS:
        for match in pattern.finditer(text):
            title = match.group(1) if match.lastindex else match.group(0)
            title = title.strip().rstrip("。，；：")
            if title and len(title) >= 2 and title not in seen:
                titles.append(title)
                seen.add(title)
    return titles


def _extract_key_sentences(text: str) -> List[str]:
    sentences = []
    seen = set()
    for pattern in KEY_SENTENCE_PATTERNS:
        for match in pattern.finditer(text):
            s = match.group(0).strip()
            if s and s not in seen:
                sentences.append(s)
                seen.add(s)
    return sentences


def _extract_risks(text: str) -> List[str]:
    risks = []
    seen = set()
    for pattern in RISK_PATTERNS:
        for match in pattern.finditer(text):
            r = match.group(0).strip()
            if r and r not in seen:
                risks.append(r)
                seen.add(r)
    return risks


def _build_single_agenda(text: str, key_sentences: List[str], risks: List[str]) -> AgendaItem:
    first_line = text.split("\n")[0][:50] if text else "综合讨论"
    return AgendaItem(
        title=first_line,
        content=text[:500],
        key_sentences=key_sentences,
        risks=risks,
    )


def _split_by_agendas(text: str, titles: List[str]) -> List[str]:
    if not titles:
        return [text]

    sections = []
    for i, title in enumerate(titles):
        try:
            start = text.index(titles[i])
        except ValueError:
            start = 0
        if i + 1 < len(titles):
            try:
                end = text.index(titles[i + 1], start + 1)
            except ValueError:
                end = len(text)
        else:
            end = len(text)
        sections.append(text[start:end])

    return sections
