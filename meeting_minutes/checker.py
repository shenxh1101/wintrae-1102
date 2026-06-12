from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Optional, Tuple

from .models import MeetingMinutes, TodoItem
from .project import ProjectManager


class Checker:
    def __init__(self, project_manager: Optional[ProjectManager] = None):
        self.pm = project_manager or ProjectManager()

    def check_todos(self, todos: List[TodoItem]) -> List[dict]:
        issues = []
        for i, todo in enumerate(todos, 1):
            missing = todo.missing_fields
            if missing:
                issues.append({
                    "index": i,
                    "task": todo.task[:60],
                    "missing": missing,
                    "assignee": todo.assignee,
                    "deadline": todo.deadline,
                })
        return issues

    def check_minutes(self, minutes: MeetingMinutes) -> dict:
        todo_issues = self.check_todos(minutes.todos)

        warnings = []
        if not minutes.title:
            warnings.append("缺少会议标题")
        if not minutes.date:
            warnings.append("缺少会议日期")
        if not minutes.attendees:
            warnings.append("缺少参会人信息")
        if not minutes.agendas:
            warnings.append("未识别到任何议题")
        if not minutes.todos:
            warnings.append("未提取到任何待办事项")

        return {
            "todo_issues": todo_issues,
            "warnings": warnings,
            "has_issues": bool(todo_issues or warnings),
            "summary": f"待办检查：{len(todo_issues)} 项缺少责任人或截止时间；{len(warnings)} 项警告",
        }

    def check_project_minutes(self, project_name: str, filename: str) -> dict:
        minutes = self.pm.load_minutes(project_name, filename)
        return self.check_minutes(minutes)

    def format_check_result(self, result: dict) -> str:
        lines = []
        lines.append("📋 导出前检查结果")
        lines.append("=" * 50)

        if result["todo_issues"]:
            lines.append("")
            lines.append("⚠️ 以下待办事项缺少责任人或截止时间：")
            for issue in result["todo_issues"]:
                missing_str = "、".join(issue["missing"])
                lines.append(f"  #{issue['index']} [{missing_str}未填写]")
                lines.append(f"     任务：{issue['task']}")
                if not issue["assignee"]:
                    lines.append(f"     责任人：❌ 缺失")
                else:
                    lines.append(f"     责任人：{issue['assignee']}")
                if not issue["deadline"]:
                    lines.append(f"     截止时间：❌ 缺失")
                else:
                    lines.append(f"     截止时间：{issue['deadline']}")

        if result["warnings"]:
            lines.append("")
            lines.append("⚡ 其他警告：")
            for w in result["warnings"]:
                lines.append(f"  - {w}")

        lines.append("")
        lines.append(f"总结：{result['summary']}")

        if result["has_issues"]:
            lines.append("")
            lines.append("💡 建议在导出前补充缺失信息")

        return "\n".join(lines)
