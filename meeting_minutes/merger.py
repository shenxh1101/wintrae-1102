from __future__ import annotations

from datetime import datetime
from typing import List, Optional

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
        deduplicate: bool = True,
    ) -> MeetingMinutes:
        all_minutes = []
        for fn in filenames:
            m = self.pm.load_minutes(project_name, fn)
            all_minutes.append(m)

        if not all_minutes:
            raise ValueError("没有可合并的会议纪要")

        merged = MeetingMinutes()
        merged.title = title or " + ".join(m.title or "未命名" for m in all_minutes)
        merged.date = all_minutes[0].date or datetime.now().strftime("%Y-%m-%d")

        seen_attendees = set()
        for m in all_minutes:
            for a in m.attendees:
                if a not in seen_attendees:
                    merged.attendees.append(a)
                    seen_attendees.add(a)

        for i, m in enumerate(all_minutes):
            prefix = f"[{m.title or f'会议{i+1}'}] "
            for seg in m.segments:
                merged.segments.append(SpeakerSegment(
                    speaker=seg.speaker,
                    content=prefix + seg.content,
                    timestamp=seg.timestamp,
                ))

        agenda_offset = 0
        for m in all_minutes:
            for agenda in m.agendas:
                merged.agendas.append(AgendaItem(
                    title=agenda.title,
                    content=agenda.content,
                    key_sentences=agenda.key_sentences,
                    risks=agenda.risks,
                ))
                agenda_offset += 1

        seen_tasks = set()
        for m in all_minutes:
            for todo in m.todos:
                task_key = todo.task.strip()[:60]
                if deduplicate and task_key in seen_tasks:
                    continue
                seen_tasks.add(task_key)
                merged.todos.append(TodoItem(
                    task=todo.task,
                    assignee=todo.assignee,
                    deadline=todo.deadline,
                    source=todo.source,
                    priority=todo.priority,
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
