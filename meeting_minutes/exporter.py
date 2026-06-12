from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from .models import MeetingMinutes, AgendaItem, TodoItem


def export_markdown(minutes: MeetingMinutes) -> str:
    lines = []

    lines.append(f"# {minutes.title or '会议纪要'}")
    lines.append("")

    if minutes.date:
        lines.append(f"**日期**：{minutes.date}")
    if minutes.attendees:
        lines.append(f"**参会人**：{', '.join(minutes.attendees)}")
    lines.append("")

    lines.append("---")
    lines.append("")

    if minutes.agendas:
        lines.append("## 议题")
        lines.append("")
        for i, agenda in enumerate(minutes.agendas, 1):
            lines.append(f"### {i}. {agenda.title}")
            lines.append("")
            if agenda.content:
                lines.append(agenda.content)
                lines.append("")
            if agenda.key_sentences:
                lines.append("**要点**：")
                for ks in agenda.key_sentences:
                    lines.append(f"- {ks}")
                lines.append("")
            if agenda.risks:
                lines.append("**风险**：")
                for r in agenda.risks:
                    lines.append(f"- ⚠️ {r}")
                lines.append("")

    if minutes.highlights:
        lines.append("## 重点")
        lines.append("")
        for h in minutes.highlights:
            lines.append(f"- 🔑 {h}")
        lines.append("")

    if minutes.risks:
        lines.append("## 风险清单")
        lines.append("")
        for r in minutes.risks:
            lines.append(f"- ⚠️ {r}")
        lines.append("")

    if minutes.todos:
        lines.append("## 待办事项")
        lines.append("")
        lines.append("| # | 任务 | 责任人 | 截止时间 | 优先级 |")
        lines.append("|---|------|--------|---------|--------|")
        for i, todo in enumerate(minutes.todos, 1):
            assignee = todo.assignee or "❌ 未指定"
            deadline = todo.deadline or "❌ 未指定"
            priority = todo.priority or "-"
            lines.append(f"| {i} | {todo.task[:60]} | {assignee} | {deadline} | {priority} |")
        lines.append("")

    if minutes.segments:
        lines.append("## 发言记录")
        lines.append("")
        for seg in minutes.segments:
            ts = f" [{seg.timestamp}]" if seg.timestamp else ""
            lines.append(f"**{seg.speaker}**{ts}：{seg.content}")
            lines.append("")

    lines.append("---")
    lines.append(f"*由 meeting-minutes 工具自动生成*")

    return "\n".join(lines)


def export_word(minutes: MeetingMinutes, output_path: Path) -> Path:
    try:
        from docx import Document
        from docx.shared import Pt, Inches, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.enum.table import WD_TABLE_ALIGNMENT
    except ImportError:
        raise ImportError("导出 Word 需要安装 python-docx：pip install python-docx")

    doc = Document()

    title_para = doc.add_heading(minutes.title or "会议纪要", level=0)
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER

    if minutes.date:
        doc.add_paragraph(f"日期：{minutes.date}")
    if minutes.attendees:
        doc.add_paragraph(f"参会人：{', '.join(minutes.attendees)}")

    doc.add_paragraph("─" * 40)

    if minutes.agendas:
        doc.add_heading("议题", level=1)
        for i, agenda in enumerate(minutes.agendas, 1):
            doc.add_heading(f"{i}. {agenda.title}", level=2)
            if agenda.content:
                doc.add_paragraph(agenda.content)
            if agenda.key_sentences:
                p = doc.add_paragraph()
                run = p.add_run("要点：")
                run.bold = True
                for ks in agenda.key_sentences:
                    doc.add_paragraph(ks, style="List Bullet")
            if agenda.risks:
                p = doc.add_paragraph()
                run = p.add_run("风险：")
                run.bold = True
                for r in agenda.risks:
                    doc.add_paragraph(f"⚠️ {r}", style="List Bullet")

    if minutes.highlights:
        doc.add_heading("重点", level=1)
        for h in minutes.highlights:
            doc.add_paragraph(f"🔑 {h}", style="List Bullet")

    if minutes.risks:
        doc.add_heading("风险清单", level=1)
        for r in minutes.risks:
            doc.add_paragraph(f"⚠️ {r}", style="List Bullet")

    if minutes.todos:
        doc.add_heading("待办事项", level=1)
        table = doc.add_table(rows=1, cols=5)
        table.style = "Table Grid"
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        headers = ["#", "任务", "责任人", "截止时间", "优先级"]
        for i, header in enumerate(headers):
            cell = table.rows[0].cells[i]
            cell.text = header
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.bold = True

        for idx, todo in enumerate(minutes.todos, 1):
            row = table.add_row()
            row.cells[0].text = str(idx)
            row.cells[1].text = todo.task[:60]
            row.cells[2].text = todo.assignee or "❌ 未指定"
            row.cells[3].text = todo.deadline or "❌ 未指定"
            row.cells[4].text = todo.priority or "-"
            if not todo.assignee or not todo.deadline:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        for run in paragraph.runs:
                            run.font.color.rgb = RGBColor(255, 0, 0)

    if minutes.segments:
        doc.add_heading("发言记录", level=1)
        for seg in minutes.segments:
            p = doc.add_paragraph()
            run = p.add_run(f"{seg.speaker}")
            run.bold = True
            ts = f" [{seg.timestamp}]" if seg.timestamp else ""
            p.add_run(f"{ts}：{seg.content}")

    doc.add_paragraph("─" * 40)
    p = doc.add_paragraph("由 meeting-minutes 工具自动生成")
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    return output_path


def export_minutes(minutes: MeetingMinutes, output_path: Path, fmt: str = "markdown") -> Path:
    fmt = fmt.lower().strip(".")
    if fmt in ("md", "markdown"):
        content = export_markdown(minutes)
        output_path = output_path.with_suffix(".md")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
        return output_path
    elif fmt in ("docx", "word"):
        output_path = output_path.with_suffix(".docx")
        return export_word(minutes, output_path)
    else:
        raise ValueError(f"不支持的导出格式：{fmt}（支持 markdown/docx）")
