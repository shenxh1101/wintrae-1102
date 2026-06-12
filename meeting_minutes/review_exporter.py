from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from collections import defaultdict

from .models import MeetingMinutes, TodoItem, TODO_STATUS
from .project import ProjectManager


@dataclass
class PeriodStats:
    period_key: str
    period_label: str
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    meeting_count: int = 0
    meetings: List[MeetingMinutes] = field(default_factory=list)
    new_agendas: List[tuple] = field(default_factory=list)
    risk_changes: Dict[str, List[str]] = field(default_factory=lambda: defaultdict(list))
    new_risks: List[tuple] = field(default_factory=list)
    resolved_risks: List[tuple] = field(default_factory=list)
    new_todos: List[TodoItem] = field(default_factory=list)
    closed_todos: List[TodoItem] = field(default_factory=list)
    in_progress_todos: List[TodoItem] = field(default_factory=list)
    delayed_todos: List[TodoItem] = field(default_factory=list)
    all_todos: List[TodoItem] = field(default_factory=list)

    def to_dict(self):
        return {
            "period_key": self.period_key,
            "period_label": self.period_label,
            "start_date": self.start_date.strftime("%Y-%m-%d") if self.start_date else None,
            "end_date": self.end_date.strftime("%Y-%m-%d") if self.end_date else None,
            "meeting_count": self.meeting_count,
            "new_agendas_count": len(self.new_agendas),
            "risks_count": len(self.new_risks),
            "new_todos_count": len(self.new_todos),
            "closed_todos_count": len(self.closed_todos),
        }


class ReviewExporter:
    def __init__(self, project_manager: Optional[ProjectManager] = None):
        self.pm = project_manager or ProjectManager()

    def generate_review(
        self,
        project_name: str,
        gran: str = "week",
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> List[PeriodStats]:
        project_dir = self.pm.get_project_dir(project_name)
        if not project_dir:
            return []

        processed_dir = project_dir / "processed"
        if not processed_dir.exists():
            return []

        all_minutes = []
        for filepath in processed_dir.iterdir():
            if filepath.suffix == ".json":
                try:
                    m = MeetingMinutes.from_json(filepath.read_text(encoding="utf-8"))
                    m.source_file = filepath.name
                    all_minutes.append(m)
                except Exception:
                    continue

        def sort_key(m):
            try:
                d = m.get_parsed_date()
                return d or datetime.min
            except Exception:
                return datetime.min

        all_minutes.sort(key=sort_key)

        dt_from = self._parse_date(date_from)
        dt_to = self._parse_date(date_to, end_of_day=True)

        all_minutes = [m for m in all_minutes if self._in_range(m, dt_from, dt_to)]

        periods = self._group_by_period(all_minutes, gran)

        return self._compute_stats(periods, all_minutes)

    def _parse_date(self, date_str: Optional[str], end_of_day: bool = False) -> Optional[datetime]:
        if not date_str:
            return None
        for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d", "%Y年%m月%d日"):
            try:
                dt = datetime.strptime(date_str, fmt)
                if end_of_day:
                    dt = dt.replace(hour=23, minute=59, second=59)
                return dt
            except ValueError:
                continue
        return None

    def _in_range(self, m: MeetingMinutes, dt_from: Optional[datetime], dt_to: Optional[datetime]) -> bool:
        try:
            d = m.get_parsed_date()
        except Exception:
            d = None
        if not d:
            d = datetime.min
        if dt_from and d < dt_from:
            return False
        if dt_to and d > dt_to:
            return False
        return True

    def _group_by_period(self, minutes: List[MeetingMinutes], gran: str) -> Dict[str, List[MeetingMinutes]]:
        groups = defaultdict(list)
        for m in minutes:
            try:
                d = m.get_parsed_date()
            except Exception:
                d = None
            if not d:
                key = "未标注日期"
            elif gran == "week":
                monday = d - timedelta(days=d.weekday())
                key = monday.strftime("%Y-W%W")
            elif gran == "month":
                key = d.strftime("%Y-%m")
            else:
                key = d.strftime("%Y-%m-%d")
            groups[key].append(m)
        return dict(sorted(groups.items()))

    def _compute_stats(
        self,
        period_groups: Dict[str, List[MeetingMinutes]],
        all_minutes: List[MeetingMinutes],
    ) -> List[PeriodStats]:
        seen_tasks = {}
        seen_risks = {}
        seen_agendas = {}
        stats_list = []

        for period_key, meetings in period_groups.items():
            gran = "week" if "W" in period_key else ("month" if "-" in period_key and period_key.count("-") == 1 else "day")
            period_label = self._format_period_label(period_key, gran)

            try:
                first_date = meetings[0].get_parsed_date() if meetings else None
                last_date = meetings[-1].get_parsed_date() if meetings else None
            except Exception:
                first_date = None
                last_date = None

            stats = PeriodStats(
                period_key=period_key,
                period_label=period_label,
                start_date=first_date,
                end_date=last_date,
                meeting_count=len(meetings),
                meetings=meetings,
            )

            period_tasks_in = set()
            period_risks_in = set()
            period_agendas_in = set()

            for m in meetings:
                for a in m.agendas:
                    ak = a.title[:40]
                    if ak not in seen_agendas:
                        seen_agendas[ak] = (a, m.title or m.source_file)
                        stats.new_agendas.append((a.title, m.title or m.source_file))
                    period_agendas_in.add(ak)

                for r in m.risks:
                    rk = r[:60]
                    if rk not in seen_risks:
                        seen_risks[rk] = "active"
                        stats.new_risks.append((r, m.title or m.source_file))
                    period_risks_in.add(rk)
                    stats.risk_changes[rk].append(m.title or m.source_file)

                for t in m.todos:
                    tk = t.task_key()
                    if tk not in seen_tasks:
                        seen_tasks[tk] = t.status or "待办"
                        stats.new_todos.append(t)
                    period_tasks_in.add(tk)
                    stats.all_todos.append(t)
                    if t.status == "已完成":
                        stats.closed_todos.append(t)
                    elif t.status == "进行中":
                        stats.in_progress_todos.append(t)
                    elif t.status == "延期":
                        stats.delayed_todos.append(t)

            for tk in list(seen_tasks.keys()):
                if tk not in period_tasks_in:
                    prev_status = seen_tasks.get(tk, "")
                    if prev_status not in ("已完成", "取消") and prev_status != "":
                        continue
                    t = self._find_todo_by_key(tk, all_minutes)
                    if t and t.status == "已完成":
                        stats.closed_todos.append(t)
                        seen_tasks[tk] = "已完成"

            for rk in list(seen_risks.keys()):
                if rk not in period_risks_in and seen_risks.get(rk) == "active":
                    r_text = self._find_risk_by_key(rk, all_minutes)
                    if r_text:
                        stats.resolved_risks.append((r_text, ""))
                        seen_risks[rk] = "resolved"

            stats_list.append(stats)

        return stats_list

    def _find_todo_by_key(self, key: str, all_minutes: List[MeetingMinutes]) -> Optional[TodoItem]:
        for m in all_minutes:
            for t in m.todos:
                if t.task_key() == key:
                    return t
        return None

    def _find_risk_by_key(self, key: str, all_minutes: List[MeetingMinutes]) -> Optional[str]:
        for m in all_minutes:
            for r in m.risks:
                if r[:60] == key:
                    return r
        return None

    def _format_period_label(self, period_key: str, gran: str) -> str:
        if gran == "week":
            try:
                year, week = period_key.split("-W")
                year = int(year)
                week = int(week)
                d = datetime(year, 1, 1) + timedelta(weeks=week-1)
                d = d - timedelta(days=d.weekday())
                end = d + timedelta(days=6)
                return f"{d.strftime('%Y年%m月%d日')} ~ {end.strftime('%m月%d日')} (第{week}周)"
            except Exception:
                return period_key
        elif gran == "month":
            try:
                year, month = period_key.split("-")
                return f"{year}年{int(month)}月"
            except Exception:
                return period_key
        return period_key

    def export_markdown(self, project_name: str, stats_list: List[PeriodStats], output_path: Optional[str] = None) -> str:
        today = datetime.now().strftime("%Y-%m-%d")
        lines = [
            f"# 📊 项目复盘报告",
            f"**项目**: {project_name}",
            f"**生成时间**: {today}",
            "",
        ]

        total_meetings = sum(s.meeting_count for s in stats_list)
        total_new_todos = sum(len(s.new_todos) for s in stats_list)
        total_closed = sum(len(s.closed_todos) for s in stats_list)
        total_risks = sum(len(s.new_risks) for s in stats_list)

        lines.extend([
            "## 📈 整体概览",
            "",
            f"- **统计周期**: {len(stats_list)} 个周期",
            f"- **会议总数**: {total_meetings} 场",
            f"- **新增待办**: {total_new_todos} 项",
            f"- **完成待办**: {total_closed} 项",
            f"- **新增风险**: {total_risks} 项",
            "",
        ])

        if total_new_todos > 0:
            rate = total_closed / total_new_todos * 100 if total_new_todos > 0 else 0
            bar_len = 20
            filled = int(bar_len * rate / 100)
            bar = "█" * filled + "░" * (bar_len - filled)
            lines.extend([
                f"- **完成率**: `[{bar}] {rate:.1f}% ({total_closed}/{total_new_todos})`",
                "",
            ])

        for stats in stats_list:
            lines.extend([
                f"## 📅 {stats.period_label}",
                "",
                f"- **会议**: {stats.meeting_count} 场",
                "  - " + ", ".join([m.title or m.source_file for m in stats.meetings]),
                "",
            ])

            if stats.new_agendas:
                lines.extend([
                    f"### 📋 新增议题 ({len(stats.new_agendas)} 项)",
                    "",
                ])
                for title, src in stats.new_agendas:
                    lines.append(f"- {title} *[{src}]*")
                lines.append("")

            if stats.new_risks or stats.resolved_risks:
                lines.extend([
                    f"### ⚠️ 风险变化",
                    "",
                ])
                if stats.new_risks:
                    lines.append(f"**新增风险 ({len(stats.new_risks)} 项)**:")
                    for r, src in stats.new_risks:
                        src_list = stats.risk_changes.get(r[:60], [src])
                        src_str = "、".join(src_list) if src_list else src
                        lines.append(f"- {r} *[{src_str}]*")
                    lines.append("")
                if stats.resolved_risks:
                    lines.append(f"**已解决风险 ({len(stats.resolved_risks)} 项)**:")
                    for r, _ in stats.resolved_risks:
                        lines.append(f"- ✅ {r}")
                    lines.append("")

            lines.extend([
                f"### ✅ 待办追踪",
                "",
            ])
            lines.append(f"| 状态 | 数量 |")
            lines.append(f"|------|------|")
            lines.append(f"| 新增 | {len(stats.new_todos)} |")
            lines.append(f"| 进行中 | {len(stats.in_progress_todos)} |")
            lines.append(f"| 已完成 | {len(stats.closed_todos)} |")
            lines.append(f"| 延期 | {len(stats.delayed_todos)} |")
            lines.append("")

            if stats.new_todos:
                lines.append("**新增待办**:")
                for t in stats.new_todos[:10]:
                    a = t.display_assignees() or "未指定"
                    d = t.display_deadlines() or "未指定"
                    lines.append(f"- [ ] {t.task} (责任人: {a} | 截止: {d})")
                if len(stats.new_todos) > 10:
                    lines.append(f"- ... 等 {len(stats.new_todos)} 项")
                lines.append("")

            if stats.closed_todos:
                lines.append("**已完成待办**:")
                for t in stats.closed_todos[:10]:
                    a = t.display_assignees() or "未指定"
                    lines.append(f"- [x] {t.task} (责任人: {a})")
                if len(stats.closed_todos) > 10:
                    lines.append(f"- ... 等 {len(stats.closed_todos)} 项")
                lines.append("")

            if stats.in_progress_todos:
                lines.append("**进行中待办**:")
                for t in stats.in_progress_todos[:10]:
                    a = t.display_assignees() or "未指定"
                    d = t.display_deadlines() or "未指定"
                    lines.append(f"- [~] {t.task} (责任人: {a} | 截止: {d})")
                if len(stats.in_progress_todos) > 10:
                    lines.append(f"- ... 等 {len(stats.in_progress_todos)} 项")
                lines.append("")

            if stats.delayed_todos:
                lines.append("**延期待办**:")
                for t in stats.delayed_todos[:10]:
                    a = t.display_assignees() or "未指定"
                    d = t.display_deadlines() or "未指定"
                    lines.append(f"- [!] {t.task} (责任人: {a} | 原截止: {d})")
                if len(stats.delayed_todos) > 10:
                    lines.append(f"- ... 等 {len(stats.delayed_todos)} 项")
                lines.append("")

        lines.extend([
            "---",
            "*本报告由会议纪要工具自动生成*",
        ])

        md_content = "\n".join(lines)

        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(md_content)

        return md_content

    def print_timeline_text(self, stats_list: List[PeriodStats], show_todos: bool = False) -> str:
        lines = []
        for i, stats in enumerate(stats_list, 1):
            marker = "└─" if i == len(stats_list) else "├─"
            lines.append(f"[{i}/{len(stats_list)}] {marker} **{stats.period_label}**")
            lines.append(f"       📅 会议 {stats.meeting_count} 场 | 议题 {len(stats.new_agendas)} 项")

            todo_total = len(stats.new_todos)
            todo_closed = len(stats.closed_todos)
            todo_inprog = len(stats.in_progress_todos)
            todo_delay = len(stats.delayed_todos)

            lines.append(f"       ✅ 待办: 新增{todo_total} / 完成{todo_closed} / 进行中{todo_inprog} / 延期{todo_delay}")

            risk_new = len(stats.new_risks)
            risk_resolved = len(stats.resolved_risks)
            lines.append(f"       ⚠️  风险: 新增{risk_new} / 解决{risk_resolved}")

            if show_todos and stats.all_todos:
                for t in stats.all_todos:
                    a = t.display_assignees() or "?"
                    d = t.display_deadlines() or "?"
                    status_icon = {"待办": "⏳", "进行中": "🔄", "已完成": "✅", "延期": "⚠️", "取消": "❌"}.get(t.status, "")
                    lines.append(f"         {status_icon} {t.task[:30]} ({a} | {d})")
            lines.append("")

        return "\n".join(lines)
