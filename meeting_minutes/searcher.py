from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Optional, Tuple

from .models import MeetingMinutes
from .project import ProjectManager


class Searcher:
    def __init__(self, project_manager: Optional[ProjectManager] = None):
        self.pm = project_manager or ProjectManager()

    def search_in_project(self, project_name: str, keyword: str) -> List[dict]:
        project_dir = self.pm.get_project_dir(project_name)
        if project_dir is None:
            return []

        results = []
        processed_dir = project_dir / "processed"
        if not processed_dir.exists():
            return results

        keyword_lower = keyword.lower()

        for filepath in processed_dir.iterdir():
            if filepath.suffix != ".json":
                continue
            try:
                minutes = MeetingMinutes.from_json(filepath.read_text(encoding="utf-8"))
            except Exception:
                continue

            matches = self._search_in_minutes(minutes, keyword_lower)
            if matches:
                results.append({
                    "file": filepath.name,
                    "title": minutes.title,
                    "date": minutes.date,
                    "matches": matches,
                })

        return results

    def search_across_projects(self, keyword: str) -> List[dict]:
        results = []
        for project_name in self.pm.list_projects():
            project_results = self.search_in_project(project_name, keyword)
            for r in project_results:
                r["project"] = project_name
            results.extend(project_results)
        return results

    def _search_in_minutes(self, minutes: MeetingMinutes, keyword: str) -> List[dict]:
        matches = []

        for agenda in minutes.agendas:
            if keyword in agenda.title.lower():
                matches.append({"type": "议题", "content": agenda.title})
            if keyword in agenda.content.lower():
                matches.append({"type": "议题内容", "content": agenda.content[:100]})
            for ks in agenda.key_sentences:
                if keyword in ks.lower():
                    matches.append({"type": "要点", "content": ks})

        for todo in minutes.todos:
            if keyword in todo.task.lower() or keyword in todo.assignee.lower():
                matches.append({"type": "待办", "content": f"{todo.task}（{todo.assignee}）"})

        for seg in minutes.segments:
            if keyword in seg.content.lower():
                matches.append({"type": "发言", "content": f"{seg.speaker}：{seg.content[:80]}"})

        for h in minutes.highlights:
            if keyword in h.lower():
                matches.append({"type": "重点", "content": h})

        for r in minutes.risks:
            if keyword in r.lower():
                matches.append({"type": "风险", "content": r})

        return matches

    def format_search_results(self, results: List[dict], keyword: str) -> str:
        if not results:
            return f"未找到与 '{keyword}' 相关的内容"

        lines = [f"🔍 搜索结果：'{keyword}'", "=" * 50]

        for result in results:
            project = result.get("project", "")
            header_parts = [result["title"]]
            if result["date"]:
                header_parts.append(result["date"])
            if project:
                header_parts.append(f"[项目: {project}]")

            lines.append("")
            lines.append(f"📄 {' | '.join(header_parts)}")
            lines.append(f"   文件：{result['file']}")

            for match in result["matches"]:
                lines.append(f"   [{match['type']}] {match['content']}")

        lines.append("")
        total = sum(len(r["matches"]) for r in results)
        lines.append(f"共 {len(results)} 个纪要、{total} 条匹配")

        return "\n".join(lines)
