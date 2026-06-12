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
            def sort_key(m):
                try:
                    d = m.get_parsed_date()
                    return d or datetime.max
                except Exception:
                    return datetime.max
            all_minutes.sort(key=sort_key)

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
                if keep_sources and not seg.meeting_source:
                    content = f"[{source_label}] " + content
                merged.segments.append(SpeakerSegment(
                    speaker=seg.speaker,
                    content=content,
                    timestamp=seg.timestamp,
                    meeting_source=seg.meeting_source or source_label,
                ))

        for m in all_minutes:
            source_label = m.title or m.source_file or "会议"
            for agenda in m.agendas:
                new_title = agenda.title
                if keep_sources and not agenda.meeting_source:
                    new_title = f"[{source_label}] {agenda.title}"
                merged.agendas.append(AgendaItem(
                    title=new_title,
                    content=agenda.content,
                    key_sentences=list(agenda.key_sentences),
                    risks=list(agenda.risks),
                    meeting_source=agenda.meeting_source or source_label,
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
                    new_sources = list(todo.get_all_sources())
                    if keep_sources and source_label not in new_sources:
                        new_sources.append(source_label)
                    merged.todos.append(TodoItem(
                        task=todo.task,
                        assignee=todo.assignee,
                        deadline=todo.deadline,
                        source=todo.source,
                        priority=todo.priority,
                        meeting_source=todo.meeting_source,
                        assignees=list(todo.assignees),
                        deadlines=list(todo.deadlines),
                        meeting_sources=new_sources,
                        agenda_source=todo.agenda_source,
                        segment_source=todo.segment_source,
                    ))

        seen_highlights = set()
        for m in all_minutes:
            source_label = m.title or m.source_file or "会议"
            for h in m.highlights:
                h_key = h
                if keep_sources:
                    h_key = f"[{source_label}] {h}"
                if h_key not in seen_highlights:
                    merged.highlights.append(h_key)
                    seen_highlights.add(h_key)

        seen_risks = {}
        for m in all_minutes:
            source_label = m.title or m.source_file or "会议"
            for r in m.risks:
                if r not in seen_risks:
                    seen_risks[r] = set()
                seen_risks[r].add(source_label)

        for r, srcs in seen_risks.items():
            if keep_sources and srcs:
                label = f"{r} [来源：{'、'.join(sorted(srcs))}]"
                merged.risks.append(label)
            else:
                merged.risks.append(r)

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
                    existing_as = set(existing.get_all_assignees())
                    for a in todo.get_all_assignees():
                        if a and a not in existing_as:
                            existing.assignees.append(a)
                            existing_as.add(a)

                    existing_ds = set(existing.get_all_deadlines())
                    for d in todo.get_all_deadlines():
                        if d and d not in existing_ds:
                            existing.deadlines.append(d)
                            existing_ds.add(d)

                    if not existing.priority and todo.priority:
                        existing.priority = todo.priority

                    if not existing.source and todo.source:
                        existing.source = todo.source

                    existing_srcs = set(existing.get_all_sources())
                    if keep_sources:
                        if source_label not in existing_srcs:
                            existing.meeting_sources.append(source_label)
                            existing_srcs.add(source_label)
                    extra_srcs = set(todo.get_all_sources())
                    for s in extra_srcs:
                        if s not in existing_srcs:
                            existing.meeting_sources.append(s)
                            existing_srcs.add(s)

                    if not existing.agenda_source and todo.agenda_source:
                        existing.agenda_source = todo.agenda_source
                    if not existing.segment_source and todo.segment_source:
                        existing.segment_source = todo.segment_source

                else:
                    new_todo = TodoItem(
                        task=todo.task,
                        assignee=todo.assignee,
                        deadline=todo.deadline,
                        source=todo.source,
                        priority=todo.priority,
                        meeting_source=todo.meeting_source,
                        assignees=list(todo.assignees),
                        deadlines=list(todo.deadlines),
                        meeting_sources=list(todo.meeting_sources),
                        agenda_source=todo.agenda_source,
                        segment_source=todo.segment_source,
                    )
                    if keep_sources:
                        src_set = set(new_todo.get_all_sources())
                        if source_label not in src_set:
                            new_todo.meeting_sources.append(source_label)
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
