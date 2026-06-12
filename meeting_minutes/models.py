from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Optional


@dataclass
class SpeakerSegment:
    speaker: str = ""
    content: str = ""
    timestamp: str = ""
    meeting_source: str = ""

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
    meeting_source: str = ""

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
    meeting_source: str = ""
    assignees: List[str] = field(default_factory=list)
    deadlines: List[str] = field(default_factory=list)
    meeting_sources: List[str] = field(default_factory=list)
    agenda_source: str = ""
    segment_source: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TodoItem":
        return cls(**data)

    @property
    def missing_fields(self) -> List[str]:
        missing = []
        effective_assignee = self.assignee or (self.assignees[0] if self.assignees else "")
        effective_deadline = self.deadline or (self.deadlines[0] if self.deadlines else "")
        if not effective_assignee:
            missing.append("责任人")
        if not effective_deadline:
            missing.append("截止时间")
        return missing

    def get_all_assignees(self) -> List[str]:
        result = list(dict.fromkeys([a for a in (self.assignee, *self.assignees) if a]))
        return result

    def get_all_deadlines(self) -> List[str]:
        result = list(dict.fromkeys([d for d in (self.deadline, *self.deadlines) if d]))
        return result

    def get_all_sources(self) -> List[str]:
        result = list(dict.fromkeys([s for s in (self.meeting_source, *self.meeting_sources) if s]))
        return result

    def display_assignees(self) -> str:
        all_a = self.get_all_assignees()
        return "、".join(all_a) if all_a else ""

    def display_deadlines(self) -> str:
        all_d = self.get_all_deadlines()
        return "、".join(all_d) if all_d else ""

    def task_key(self) -> str:
        STOPWORDS = {"的", "了", "是", "我", "你", "他", "她", "它", "们", "这个", "那个", "这", "那", "就", "都", "就", "要", "去", "做", "搞", "弄", "好", "完", "成", "完成", "做好", "搞定", "一下", "把", "给", "让", "请", "请把", "工作", "任务", "一下", "把", "给", "让", "请", "需要", "必须", "应该", "要", "需", "须"}
        core = re.sub(r"""[，,。.；;！!？?\s、·~`!@#$%^&*()_+=\[\]\{\}|\\:;"'<>,.?/]""", "", self.task)
        for w in STOPWORDS:
            core = core.replace(w, "")
        return core[:40]


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
    source_file: str = ""

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
            source_file=data.get("source_file", ""),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "MeetingMinutes":
        return cls.from_dict(json.loads(json_str))

    @staticmethod
    def parse_date(date_str: str) -> Optional[str]:
        if not date_str:
            return None
        date_formats = [
            "%Y-%m-%d",
            "%Y%m%d",
            "%Y/%m/%d",
            "%Y年%m月%d日",
            "%Y年%m月%d",
        ]
        for fmt in date_formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                continue
        match = re.search(r"(\d{4})[-/年]?(\d{1,2})[-/月]?(\d{1,2})", date_str)
        if match:
            try:
                dt = datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
                return dt.strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                pass
        return None

    def get_parsed_date(self) -> Optional[datetime]:
        date_formats = [
            "%Y-%m-%d",
            "%Y%m%d",
            "%Y/%m/%d",
            "%Y年%m月%d日",
            "%Y年%m月%d",
        ]
        for fmt in date_formats:
            try:
                return datetime.strptime(self.date, fmt)
            except (ValueError, TypeError):
                continue
        match = re.search(r"(\d{4})[-/年]?(\d{1,2})[-/月]?(\d{1,2})", self.date)
        if match:
            try:
                return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except (ValueError, TypeError):
                pass
        return None

    def speakers(self) -> List[str]:
        seen = set()
        result = []
        for seg in self.segments:
            if seg.speaker and seg.speaker not in seen:
                result.append(seg.speaker)
                seen.add(seg.speaker)
        return result

    def todos_with_missing(self) -> List[tuple]:
        return [(i + 1, t) for i, t in enumerate(self.todos) if t.missing_fields]

    def update_todo(self, index: int, assignee: Optional[str] = None, deadline: Optional[str] = None) -> bool:
        if index < 1 or index > len(self.todos):
            return False
        todo = self.todos[index - 1]
        if assignee is not None:
            todo.assignee = assignee
        if deadline is not None:
            todo.deadline = deadline
        return True
