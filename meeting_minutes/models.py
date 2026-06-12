from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import List


@dataclass
class SpeakerSegment:
    speaker: str = ""
    content: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SpeakerSegment":
        return cls(**data)


@dataclass
class AgendaItem:
    title: str = ""
    content: str = ""
    key_sentences: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AgendaItem":
        return cls(**data)


@dataclass
class TodoItem:
    task: str = ""
    assignee: str = ""
    deadline: str = ""
    source: str = ""
    priority: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TodoItem":
        return cls(**data)

    @property
    def missing_fields(self) -> List[str]:
        missing = []
        if not self.assignee:
            missing.append("责任人")
        if not self.deadline:
            missing.append("截止时间")
        return missing


@dataclass
class MeetingMinutes:
    title: str = ""
    date: str = ""
    attendees: List[str] = field(default_factory=list)
    raw_text: str = ""
    cleaned_text: str = ""
    segments: List[SpeakerSegment] = field(default_factory=list)
    agendas: List[AgendaItem] = field(default_factory=list)
    todos: List[TodoItem] = field(default_factory=list)
    highlights: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["segments"] = [s.to_dict() for s in self.segments]
        d["agendas"] = [a.to_dict() for a in self.agendas]
        d["todos"] = [t.to_dict() for t in self.todos]
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, data: dict) -> "MeetingMinutes":
        segments = [SpeakerSegment.from_dict(s) for s in data.get("segments", [])]
        agendas = [AgendaItem.from_dict(a) for a in data.get("agendas", [])]
        todos = [TodoItem.from_dict(t) for t in data.get("todos", [])]
        return cls(
            title=data.get("title", ""),
            date=data.get("date", ""),
            attendees=data.get("attendees", []),
            raw_text=data.get("raw_text", ""),
            cleaned_text=data.get("cleaned_text", ""),
            segments=segments,
            agendas=agendas,
            todos=todos,
            highlights=data.get("highlights", []),
            risks=data.get("risks", []),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "MeetingMinutes":
        return cls.from_dict(json.loads(json_str))
