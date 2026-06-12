from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Dict

from .models import MeetingMinutes, SpeakerSegment, AgendaItem, TodoItem
from .project import ProjectManager


class Merger:
    def __init__(self, project_manager: Optional[ProjectManager] = None):
        self.pm = project_manager or ProjectManager()

    def merge_minutes(
        self,
        project_name: str,
        filenames: List[str],
        title: Optional[str] = None,
        sort_by_date: bool = True,
        keep_sources: bool = True,
        smart_merge_todos: bool = True,
    ) -> MeetingMinutes:
        all_minutes = []
        for fn in filenames:
            m = self.pm.load_minutes(project_name, fn)
            m.source_file = fn
            all_minutes.append(m)

        if not all_minutes:
            raise ValueError("没有可合并的会议纪要")

        if sort_by_date:
            all_minutes.sort(
                key=lambda m: m.parse_date() or datetime.max
            )

        merged = MeetingMinutes()
        merged.title = title or f"{all_minutes[0].title or '未命名'} + 等{len(all_minutes)}场会议"
        merged.date = all_minutes[-1].date or datetime.now().strftime("%Y-%m-%d")

        seen_attendees = set()
        for m in all_minutes:
            for a in m.attendees:
                if a not in seen_attendees:
                    merged.attendees.append(a)
                    seen_attendees.add(a)

        for m in all_minutes:
            source_label = m.title or m.source_file or "会议"
            for seg in m.segments:
                content = seg.content
                if keep_sources:
                    content = f"[{source_label}] " + content
                merged.segments.append(SpeakerSegment(
                    speaker=seg.speaker,
                    content=content,
                    timestamp=seg.timestamp,
                ))

        for m in all_minutes:
            for agenda in m.agendas:
                merged.agendas.append(AgendaItem(
                    title=agenda.title,
                    content=agenda.content,
                    key_sentences=agenda.key_sentences,
                    risks=agenda.risks,
                ))

        if smart_merge_todos:
            merged.todos = self._smart_merge_todos(all_minutes, keep_sources)
        else:
            seen_tasks = set()
            for m in all_minutes:
                source_label = m.title or m.source_file or "会议"
                for todo in m.todos:
                    task_key = todo.task_key()
                    if task_key in seen_tasks:
                        continue
                    seen_tasks.add(task_key)
                    if keep_sources and not todo.meeting_source:
                        todo.meeting_source = source_label
                    merged.todos.append(TodoItem(
                        task=todo.task,
                        assignee=todo.assignee,
                        deadline=todo.deadline,
                        source=todo.source,
                        priority=todo.priority,
                        meeting_source=todo.meeting_source,
                    ))

        seen_highlights = set()
        for m in all_minutes:
            for h in m.highlights:
                if h not in seen_highlights:
                    merged.highlights.append(h)
                    seen_highlights.add(h)

        seen_risks = set()
        for m in all_minutes:
            for r in m.risks:
                if r not in seen_risks:
                    merged.risks.append(r)
                    seen_risks.add(r)

        return merged

    def _smart_merge_todos(
        self,
        all_minutes: List[MeetingMinutes],
        keep_sources: bool,
    ) -> List[TodoItem]:
        todo_map: Dict[str, TodoItem] = {}

        for m in all_minutes:
            source_label = m.title or m.source_file or "会议"
            for todo in m.todos:
                key = todo.task_key()
                if key in todo_map:
                    existing = todo_map[key]
                    if not existing.assignee and todo.assignee:
                        existing.assignee = todo.assignee
                    if not existing.deadline and todo.deadline:
                        existing.deadline = todo.deadline
                    if not existing.priority and todo.priority:
                        existing.priority = todo.priority
                    if keep_sources:
                        sources = {s.strip() for s in existing.meeting_source.split("|") if s.strip()}
                        sources.add(source_label)
                        existing.meeting_source = " | ".join(sorted(sources))
                else:
                    new_todo = TodoItem(
                        task=todo.task,
                        assignee=todo.assignee,
                        deadline=todo.deadline,
                        source=todo.source,
                        priority=todo.priority,
                    )
                    if keep_sources:
                        new_todo.meeting_source = source_label
                    todo_map[key] = new_todo

        return list(todo_map.values())

    def merge_raw_transcripts(
        self,
        project_name: str,
        raw_files: List[str],
        output_name: Optional[str] = None,
    ) -> str:
        combined_parts = []
        for rf in raw_files:
            content = self.pm.load_raw(project_name, rf)
            separator = f"\n{'='*60}\n【文件：{rf}】\n{'='*60}\n"
            combined_parts.append(separator + content)

        combined = "\n".join(combined_parts)

        if output_name:
            project_dir = self.pm.get_project_dir(project_name)
            if project_dir:
                dest = project_dir / "raw" / output_name
                dest.write_text(combined, encoding="utf-8")

        return combined
