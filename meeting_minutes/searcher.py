from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional, Tuple

from .models import MeetingMinutes
from .project import ProjectManager


class Searcher:
    def __init__(self, project_manager: Optional[ProjectManager] = None):
        self.pm = project_manager or ProjectManager()

    def search(
        self,
        keyword: str = "",
        project_name: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        assignee: Optional[str] = None,
        types: Optional[List[str]] = None,
    ) -> List[dict]:
        if project_name:
            projects = [project_name]
        else:
            projects = self.pm.list_projects()

        all_results = []
        for pname in projects:
            project_results = self._search_in_project(
                pname, keyword, date_from, date_to, assignee, types
            )
            all_results.extend(project_results)

        all_results.sort(
            key=lambda r: r.get("date_parsed", datetime.min),
            reverse=True
        )
        return all_results

    def _search_in_project(
        self,
        project_name: str,
        keyword: str,
        date_from: Optional[str],
        date_to: Optional[str],
        assignee: Optional[str],
        types: Optional[List[str]],
    ) -> List[dict]:
        project_dir = self.pm.get_project_dir(project_name)
        if project_dir is None:
            return []

        processed_dir = project_dir / "processed"
        if not processed_dir.exists():
            return []

        dt_from = self._parse_date_filter(date_from)
        dt_to = self._parse_date_filter(date_to, end_of_day=True)

        keyword_lower = keyword.lower() if keyword else ""
        assignee_lower = assignee.lower() if assignee else ""

        results = []
        for filepath in processed_dir.iterdir():
            if filepath.suffix != ".json":
                continue
            try:
                minutes = MeetingMinutes.from_json(filepath.read_text(encoding="utf-8"))
            except Exception:
                continue

            minutes.source_file = filepath.name
            date_parsed = minutes.parse_date()

            if date_from and dt_from and date_parsed and date_parsed < dt_from:
                continue
            if date_to and dt_to and date_parsed and date_parsed > dt_to:
                continue

            matches = self._search_in_minutes(
                minutes, keyword_lower, assignee_lower, types
            )
            if matches:
                results.append({
                    "project": project_name,
                    "file": filepath.name,
                    "title": minutes.title,
                    "date": minutes.date,
                    "date_parsed": date_parsed or datetime.min,
                    "speakers": minutes.speakers(),
                    "matches": matches,
                })

        return results

    def _search_in_minutes(
        self,
        minutes: MeetingMinutes,
        keyword: str,
        assignee: str,
        types: Optional[List[str]],
    ) -> List[dict]:
        matches = []
        type_set = set(t.lower() for t in types) if types else None

        all_text = "\n".join(s.content for s in minutes.segments)

        for agenda in minutes.agendas:
            if self._should_include_type("议题", type_set):
                if self._match_keyword(agenda.title, keyword):
                    ctx = self._get_context(all_text, agenda.title, 40)
                    matches.append({
                        "type": "议题",
                        "content": agenda.title,
                        "context": ctx,
                    })
                if self._match_keyword(agenda.content, keyword):
                    ctx = self._get_context(agenda.content, keyword, 60) if keyword else agenda.content[:80]
                    matches.append({
                        "type": "议题内容",
                        "content": agenda.content[:100],
                        "context": ctx,
                    })
                for ks in agenda.key_sentences:
                    if self._should_include_type("要点", type_set) and self._match_keyword(ks, keyword):
                        ctx = self._get_context(all_text, ks, 40)
                        matches.append({
                            "type": "要点",
                            "content": ks,
                            "context": ctx,
                        })
                for r in agenda.risks:
                    if self._should_include_type("风险", type_set) and self._match_keyword(r, keyword):
                        ctx = self._get_context(all_text, r, 40)
                        matches.append({
                            "type": "风险",
                            "content": r,
                            "context": ctx,
                        })

        for todo in minutes.todos:
            if self._should_include_type("待办", type_set):
                task_match = self._match_keyword(todo.task, keyword)
                assignee_match = (not assignee) or (assignee in todo.assignee.lower())
                if task_match or assignee_match:
                    ctx = self._get_context(all_text, todo.task, 40)
                    matches.append({
                        "type": "待办",
                        "content": todo.task,
                        "context": ctx,
                        "assignee": todo.assignee,
                        "deadline": todo.deadline,
                    })

        if self._should_include_type("发言", type_set):
            for seg in minutes.segments:
                if self._match_keyword(seg.content, keyword):
                    ctx = self._get_context(seg.content, keyword, 50) if keyword else seg.content[:80]
                    matches.append({
                        "type": "发言",
                        "content": f"{seg.speaker}：{seg.content[:80]}",
                        "context": ctx,
                        "speaker": seg.speaker,
                    })

        if self._should_include_type("重点", type_set):
            for h in minutes.highlights:
                if self._match_keyword(h, keyword):
                    ctx = self._get_context(all_text, h, 40)
                    matches.append({
                        "type": "重点",
                        "content": h,
                        "context": ctx,
                    })

        if self._should_include_type("风险", type_set):
            for r in minutes.risks:
                if self._match_keyword(r, keyword):
                    ctx = self._get_context(all_text, r, 40)
                    matches.append({
                        "type": "风险",
                        "content": r,
                        "context": ctx,
                    })

        return matches

    def _match_keyword(self, text: str, keyword: str) -> bool:
        if not keyword:
            return True
        return keyword in text.lower()

    def _should_include_type(self, ttype: str, type_set: Optional[set]) -> bool:
        if type_set is None:
            return True
        return ttype.lower() in type_set

    def _get_context(self, full_text: str, match_text: str, window: int = 50) -> str:
        if not match_text:
            return ""
        idx = full_text.find(match_text)
        if idx < 0:
            return match_text[:window * 2]
        start = max(0, idx - window)
        end = min(len(full_text), idx + len(match_text) + window)
        ctx = full_text[start:end]
        if start > 0:
            ctx = "..." + ctx
        if end < len(full_text):
            ctx = ctx + "..."
        return ctx

    def _parse_date_filter(self, date_str: Optional[str], end_of_day: bool = False) -> Optional[datetime]:
        if not date_str:
            return None
        formats = ["%Y-%m-%d", "%Y%m%d", "%Y/%m/%d", "%Y年%m月%d日"]
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                if end_of_day:
                    dt = dt.replace(hour=23, minute=59, second=59)
                return dt
            except ValueError:
                continue
        match = re.search(r"(\d{4})[-/年]?(\d{1,2})[-/月]?(\d{1,2})", date_str)
        if match:
            try:
                dt = datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
                if end_of_day:
                    dt = dt.replace(hour=23, minute=59, second=59)
                return dt
            except (ValueError, TypeError):
                pass
        return None

    def format_search_results(self, results: List[dict], keyword: str) -> str:
        if not results:
            return f"[yellow]未找到与 '{keyword}' 相关的内容[/]"

        lines = [f"🔍 搜索结果：[bold]'{keyword}'[/]", "=" * 60]

        total_matches = 0
        for result in results:
            header_parts = [result["title"] or "未命名"]
            if result["date"]:
                header_parts.append(f"[dim]{result['date']}[/]")
            header_parts.append(f"[cyan][项目: {result['project']}][/]")

            lines.append("")
            lines.append(f"📄 {' | '.join(header_parts)}")
            lines.append(f"   文件：[dim]{result['file']}[/]")
            if result["speakers"]:
                lines.append(f"   参会：[dim]{', '.join(result['speakers'])}[/]")

            for i, match in enumerate(result["matches"], 1):
                type_colors = {
                    "议题": "blue", "要点": "green", "风险": "red",
                    "待办": "yellow", "发言": "magenta", "重点": "cyan",
                    "议题内容": "blue",
                }
                color = type_colors.get(match["type"], "white")
                lines.append(f"   [{color}]{i:>2}. [{match['type']}][/{color}] {match['content'][:80]}")
                if match.get("context"):
                    ctx = match["context"].replace("\n", " ")
                    lines.append(f"       [dim]上下文：{ctx[:120]}[/]")
                if match.get("assignee"):
                    assignee = match["assignee"] or "❌ 未指定"
                    deadline = match.get("deadline", "") or "❌ 未指定"
                    lines.append(f"       [dim]→ {assignee} | {deadline}[/]")
                if match.get("speaker"):
                    lines.append(f"       [dim]发言人：{match['speaker']}[/]")

            total_matches += len(result["matches"])

        lines.append("")
        lines.append(f"共 {len(results)} 个纪要、{total_matches} 条匹配")

        return "\n".join(lines)
