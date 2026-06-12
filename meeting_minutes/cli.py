from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from .models import MeetingMinutes
from .project import ProjectManager
from .cleaner import clean_text, clean_segments
from .splitter import split_by_speakers, merge_short_segments
from .summarizer import extract_agendas, extract_highlights, extract_risks
from .todo_extractor import extract_todos
from .exporter import export_minutes
from .checker import Checker
from .searcher import Searcher
from .merger import Merger

console = Console()
pm = ProjectManager()


@click.group()
@click.version_option(version="1.1.0", prog_name="meeting-minutes")
def cli():
    """会议纪要命令行工具 - 自动整理录音转写文本"""
    pass


@cli.command()
@click.argument("name")
@click.option("--base-dir", default=None, help="项目存储根目录")
def init(name: str, base_dir: Optional[str]):
    """初始化项目目录"""
    global pm
    if base_dir:
        pm = ProjectManager(Path(base_dir))

    try:
        project_dir = pm.init_project(name)
        console.print(Panel(
            f"项目 [bold green]{name}[/] 初始化成功！\n\n"
            f"目录结构：\n"
            f"  📁 {project_dir}\n"
            f"  📁 {project_dir / 'raw'}        - 原始转写文本\n"
            f"  📁 {project_dir / 'processed'}  - 处理后的纪要\n"
            f"  📁 {project_dir / 'exports'}    - 导出文件",
            title="✅ 初始化完成",
        ))
    except Exception as e:
        console.print(f"[bold red]初始化失败：{e}[/]")
        sys.exit(1)


@cli.command()
@click.argument("project")
@click.argument("file", type=click.Path(exists=True))
@click.option("--name", default=None, help="会议名称（默认使用文件名）")
@click.option("--date", default=None, help="会议日期（格式：YYYY-MM-DD）")
@click.option("--attendees", multiple=True, help="参会人（可多次使用）")
def import_file(project: str, file: str, name: Optional[str], date: Optional[str], attendees: tuple):
    """导入转写文本到项目"""
    try:
        dest = pm.import_transcript(project, file, name)
        meeting_name = name or Path(file).stem
        meeting_date = date or datetime.now().strftime("%Y-%m-%d")
        attendee_list = list(attendees) if attendees else []

        text = Path(file).read_text(encoding="utf-8")
        segments = split_by_speakers(text)
        cleaned_segments = clean_segments(segments)
        cleaned_text = clean_text(text)

        minutes = MeetingMinutes(
            title=meeting_name,
            date=meeting_date,
            attendees=attendee_list,
            raw_text=text,
            cleaned_text=cleaned_text,
            segments=cleaned_segments,
            source_file=dest.name,
        )
        pm.save_minutes(project, minutes, f"{meeting_name}_{meeting_date}.json")

        console.print(f"[green]✅ 已导入到：{dest}[/]")
        if segments:
            speakers = minutes.speakers()
            console.print(f"[dim]识别发言人：{', '.join(speakers)} ({len(segments)} 段)[/]")

    except FileNotFoundError as e:
        console.print(f"[bold red]{e}[/]")
        sys.exit(1)


@cli.command()
@click.argument("project")
@click.option("--file", "-f", default=None, help="指定原始文件名")
@click.option("--fillers", multiple=True, help="自定义口头禅（可多次使用）")
@click.option("--output", "-o", default=None, help="输出文件名")
def clean(project: str, file: Optional[str], fillers: tuple, output: Optional[str]):
    """去除口头禅，清洗转写文本"""
    try:
        if file:
            text = pm.load_raw(project, file)
        else:
            raw_files = pm.list_raw_files(project)
            if not raw_files:
                console.print("[bold red]没有可用的原始文件[/]")
                sys.exit(1)
            if len(raw_files) == 1:
                text = pm.load_raw(project, raw_files[0])
                file = raw_files[0]
            else:
                console.print("[yellow]多个原始文件，请用 --file 指定：[/]")
                for rf in raw_files:
                    console.print(f"  - {rf}")
                sys.exit(1)

        custom = list(fillers) if fillers else None
        cleaned = clean_text(text, custom_fillers=custom)

        segments = split_by_speakers(text)
        cleaned_segments = clean_segments(segments, custom_fillers=custom)

        minutes = MeetingMinutes(
            title=Path(file).stem if file else "会议",
            date=datetime.now().strftime("%Y-%m-%d"),
            raw_text=text,
            cleaned_text=cleaned,
            segments=cleaned_segments,
        )

        saved = pm.save_minutes(project, minutes, output)
        speakers = minutes.speakers()
        console.print(Panel(
            f"原始字数：{len(text)}\n"
            f"清洗后字数：{len(cleaned)}\n"
            f"减少：{len(text) - len(cleaned)} 字符\n"
            f"识别发言段：{len(cleaned_segments)} 段\n"
            f"发言人：{', '.join(speakers)}",
            title="🧹 清洗完成",
        ))
        console.print(f"[green]已保存：{saved}[/]")

    except FileNotFoundError as e:
        console.print(f"[bold red]{e}[/]")
        sys.exit(1)


@cli.command()
@click.argument("project")
@click.option("--file", "-f", default=None, help="指定已处理的纪要文件")
@click.option("--input-raw", default=None, help="指定原始文件名进行完整处理")
@click.option("--merge-threshold", default=10, help="合并短段落的字数阈值")
def split(project: str, file: Optional[str], input_raw: Optional[str], merge_threshold: int):
    """按发言人分段（支持 张三：、【李四】、[王五]、发言人1 等格式）"""
    try:
        if input_raw:
            text = pm.load_raw(project, input_raw)
            segments = split_by_speakers(text)
            cleaned_segments = clean_segments(segments)
            merged = merge_short_segments(cleaned_segments, min_length=merge_threshold)

            minutes = MeetingMinutes(
                title=Path(input_raw).stem,
                date=datetime.now().strftime("%Y-%m-%d"),
                raw_text=text,
                cleaned_text=clean_text(text),
                segments=merged,
            )
        elif file:
            minutes = pm.load_minutes(project, file)
            text = minutes.raw_text or minutes.cleaned_text
            if not text:
                console.print("[bold red]纪要中没有文本内容[/]")
                sys.exit(1)
            segments = split_by_speakers(text)
            cleaned_segments = clean_segments(segments)
            merged = merge_short_segments(cleaned_segments, min_length=merge_threshold)
            minutes.segments = merged
        else:
            raw_files = pm.list_raw_files(project)
            if not raw_files:
                console.print("[bold red]没有可用的文件，请用 --file 或 --input-raw 指定[/]")
                sys.exit(1)
            console.print("[yellow]请指定文件：[/]")
            for rf in raw_files:
                console.print(f"  原始文件：{rf}")
            processed_files = pm.list_minutes(project)
            for pf in processed_files:
                console.print(f"  处理文件：{pf}")
            sys.exit(1)

        saved = pm.save_minutes(project, minutes)
        speakers = minutes.speakers()

        table = Table(title=f"📝 发言分段结果（{len(speakers)} 位发言人：{', '.join(speakers)}）")
        table.add_column("#", style="dim", width=4)
        table.add_column("发言人", style="cyan", width=14)
        table.add_column("时间", style="dim", width=10)
        table.add_column("内容", width=50)

        for i, seg in enumerate(minutes.segments, 1):
            table.add_row(str(i), seg.speaker, seg.timestamp, seg.content[:80] + ("..." if len(seg.content) > 80 else ""))

        console.print(table)
        console.print(f"\n[green]已保存：{saved}[/]")

    except FileNotFoundError as e:
        console.print(f"[bold red]{e}[/]")
        sys.exit(1)


@cli.command()
@click.argument("project")
@click.option("--file", "-f", required=True, help="指定已处理的纪要文件")
@click.option("--highlight", is_flag=True, help="同时标记重点句")
@click.option("--risk", is_flag=True, help="同时生成风险清单")
def summary(project: str, file: str, highlight: bool, risk: bool):
    """识别议题标题，提取摘要"""
    try:
        minutes = pm.load_minutes(project, file)

        text = minutes.cleaned_text or minutes.raw_text
        agendas = extract_agendas(minutes.segments, text)
        minutes.agendas = agendas

        if highlight:
            minutes.highlights = extract_highlights(minutes.segments, text)

        if risk:
            minutes.risks = extract_risks(minutes.segments, text)

        pm.save_minutes(project, minutes, file)

        console.print(Panel("议题摘要", title="📊 Summary"))

        for i, agenda in enumerate(agendas, 1):
            console.print(f"\n[bold cyan]{i}. {agenda.title}[/]")
            if agenda.content:
                console.print(f"   {agenda.content[:100]}{'...' if len(agenda.content) > 100 else ''}")
            if agenda.key_sentences:
                console.print("   [yellow]要点：[/]")
                for ks in agenda.key_sentences:
                    console.print(f"     • {ks}")
            if agenda.risks:
                console.print("   [red]风险：[/]")
                for r in agenda.risks:
                    console.print(f"     ⚠️ {r}")

        if highlight and minutes.highlights:
            console.print("\n[bold green]🔑 重点句：[/]")
            for h in minutes.highlights:
                console.print(f"  • {h}")

        if risk and minutes.risks:
            console.print("\n[bold red]⚠️ 风险清单：[/]")
            for r in minutes.risks:
                console.print(f"  • {r}")

        console.print(f"\n[green]已更新：{file}[/]")

    except FileNotFoundError as e:
        console.print(f"[bold red]{e}[/]")
        sys.exit(1)


@cli.command()
@click.argument("project")
@click.option("--file", "-f", required=True, help="指定已处理的纪要文件")
def todo(project: str, file: str):
    """提取待办事项、责任人和截止时间"""
    try:
        minutes = pm.load_minutes(project, file)

        text = minutes.cleaned_text or minutes.raw_text
        todos = extract_todos(minutes.segments, text)
        minutes.todos = todos

        pm.save_minutes(project, minutes, file)

        if not todos:
            console.print("[yellow]未识别到待办事项[/]")
            return

        has_source = any(t.meeting_source for t in todos)

        table = Table(title="✅ 待办事项")
        table.add_column("#", style="dim", width=4)
        table.add_column("任务", width=35)
        table.add_column("责任人", style="cyan", width=10)
        table.add_column("截止时间", style="yellow", width=14)
        table.add_column("优先级", style="red", width=8)
        table.add_column("来源", style="dim", width=10)
        if has_source:
            table.add_column("会议", style="magenta", width=18)

        for i, t in enumerate(todos, 1):
            assignee = t.assignee or "[red]❌ 缺失[/]"
            deadline = t.deadline or "[red]❌ 缺失[/]"
            priority = t.priority or "-"
            source = t.source or "-"
            row_vals = [str(i), t.task[:50], assignee, deadline, priority, source]
            if has_source:
                row_vals.append(t.meeting_source or "-")
            table.add_row(*row_vals)

        console.print(table)

        checker = Checker()
        issues = checker.check_todos(todos)
        if issues:
            console.print(f"\n[yellow]⚠️ {len(issues)} 项待办缺少责任人或截止时间[/]")
            console.print(f"[dim]使用 mm review {project} -f {file} 可快速补全信息[/]")

        console.print(f"\n[green]已更新：{file}[/]")

    except FileNotFoundError as e:
        console.print(f"[bold red]{e}[/]")
        sys.exit(1)


@cli.command()
@click.argument("project")
@click.option("--file", "-f", required=True, help="指定已处理的纪要文件")
def review(project: str, file: str):
    """集中查看并编辑纪要信息（议题、重点、风险、待办）"""
    try:
        minutes = pm.load_minutes(project, file)
        changed = False

        while True:
            console.print("\n" + "=" * 60)
            console.print(f"📋 纪要审核：[bold cyan]{minutes.title or '未命名'}[/] | {minutes.date or '日期未设置'}")
            console.print("=" * 60)

            if minutes.agendas:
                console.print("\n[bold]📌 议题：[/]")
                for i, agenda in enumerate(minutes.agendas, 1):
                    console.print(f"  {i:>2}. {agenda.title}")
                    if agenda.key_sentences:
                        console.print(f"       [yellow]要点：{len(agenda.key_sentences)} 条[/]")
                    if agenda.risks:
                        console.print(f"       [red]风险：{len(agenda.risks)} 条[/]")

            if minutes.highlights:
                console.print(f"\n[bold]🔑 重点：[/][green]{len(minutes.highlights)}[/] 条")

            if minutes.risks:
                console.print(f"\n[bold]⚠️  风险：[/][red]{len(minutes.risks)}[/] 条")

            if minutes.todos:
                console.print(f"\n[bold]📝 待办：[/][yellow]{len(minutes.todos)}[/] 条")
                missing = minutes.todos_with_missing()
                if missing:
                    console.print(f"[red]  ⚠️ {len(missing)} 项待办缺少责任人或截止时间：[/]")
                    table = Table(show_header=True, header_style="bold")
                    table.add_column("#", style="dim", width=4)
                    table.add_column("任务", width=40)
                    table.add_column("责任人", style="cyan", width=10)
                    table.add_column("截止时间", style="yellow", width=14)
                    for idx, todo in missing:
                        assignee = todo.assignee or "[red]❌[/]"
                        deadline = todo.deadline or "[red]❌[/]"
                        table.add_row(str(idx), todo.task[:50], assignee, deadline)
                    console.print(table)

            console.print("\n" + "─" * 60)
            console.print("[bold]操作选项：[/]")
            console.print("  [cyan]1[/]. 按编号编辑待办责任人")
            console.print("  [cyan]2[/]. 按编号编辑待办截止时间")
            console.print("  [cyan]3[/]. 同时编辑责任人 + 截止时间")
            console.print("  [cyan]4[/]. 批量补全所有缺失的待办")
            console.print("  [cyan]s[/]. 保存并退出")
            console.print("  [cyan]q[/]. 不保存退出")

            choice = click.prompt("\n请选择操作", type=str).strip().lower()

            if choice == "1":
                idx = click.prompt("请输入待办编号", type=int)
                if idx < 1 or idx > len(minutes.todos):
                    console.print("[bold red]编号超出范围[/]")
                    continue
                assignee = click.prompt("请输入责任人姓名", type=str).strip()
                if minutes.update_todo(idx, assignee=assignee):
                    changed = True
                    console.print(f"[green]✅ 已更新 #{idx} 的责任人为：{assignee}[/]")

            elif choice == "2":
                idx = click.prompt("请输入待办编号", type=int)
                if idx < 1 or idx > len(minutes.todos):
                    console.print("[bold red]编号超出范围[/]")
                    continue
                deadline = click.prompt("请输入截止时间（如：2026-06-20 或 6月20日）", type=str).strip()
                if minutes.update_todo(idx, deadline=deadline):
                    changed = True
                    console.print(f"[green]✅ 已更新 #{idx} 的截止时间为：{deadline}[/]")

            elif choice == "3":
                idx = click.prompt("请输入待办编号", type=int)
                if idx < 1 or idx > len(minutes.todos):
                    console.print("[bold red]编号超出范围[/]")
                    continue
                assignee = click.prompt("请输入责任人姓名", type=str).strip()
                deadline = click.prompt("请输入截止时间", type=str).strip()
                if minutes.update_todo(idx, assignee=assignee, deadline=deadline):
                    changed = True
                    console.print(f"[green]✅ 已更新 #{idx}[/]")

            elif choice == "4":
                missing = minutes.todos_with_missing()
                if not missing:
                    console.print("[yellow]没有需要补全的待办[/]")
                    continue
                console.print(f"\n将依次补全 {len(missing)} 项待办：")
                for idx, todo in missing:
                    console.print(f"\n[bold]#{idx}[/]：{todo.task[:60]}")
                    if not todo.assignee:
                        assignee = click.prompt(f"  责任人", type=str).strip()
                        if assignee:
                            minutes.update_todo(idx, assignee=assignee)
                            changed = True
                    if not todo.deadline:
                        deadline = click.prompt(f"  截止时间", type=str).strip()
                        if deadline:
                            minutes.update_todo(idx, deadline=deadline)
                            changed = True
                console.print("\n[green]✅ 批量补全完成[/]")

            elif choice == "s":
                if changed:
                    pm.save_minutes(project, minutes, file)
                    console.print(f"\n[green]✅ 已保存修改到：{file}[/]")
                else:
                    console.print("\n[yellow]没有修改，无需保存[/]")
                break

            elif choice == "q":
                if changed:
                    confirm = click.confirm("有未保存的修改，确定退出吗？", default=False)
                    if not confirm:
                        continue
                console.print("\n[yellow]已退出[/]")
                break

            else:
                console.print("[bold red]无效选项，请重新选择[/]")

    except FileNotFoundError as e:
        console.print(f"[bold red]{e}[/]")
        sys.exit(1)


@cli.command()
@click.argument("project")
@click.option("--file", "-f", default=None, help="指定已处理的纪要文件")
@click.option("--format", "-t", "fmt", default="markdown", type=click.Choice(["markdown", "docx"]), help="导出格式")
@click.option("--output", "-o", default=None, help="输出文件名")
@click.option("--no-check", is_flag=True, help="跳过导出前检查")
def export(project: str, file: Optional[str], fmt: str, output: Optional[str], no_check: bool):
    """导出为 Markdown 或 Word 文档"""
    try:
        if not file:
            processed_files = pm.list_minutes(project)
            if not processed_files:
                console.print("[bold red]没有可导出的纪要[/]")
                sys.exit(1)
            if len(processed_files) == 1:
                file = processed_files[0]
            else:
                console.print("[yellow]请用 --file 指定要导出的纪要：[/]")
                for pf in processed_files:
                    console.print(f"  - {pf}")
                sys.exit(1)

        minutes = pm.load_minutes(project, file)

        if not no_check:
            checker = Checker()
            result = checker.check_minutes(minutes)
            console.print(checker.format_check_result(result))
            if result["has_issues"]:
                confirm = click.confirm("\n存在检查问题，是否继续导出？", default=False)
                if not confirm:
                    console.print("[yellow]已取消导出[/]")
                    return

        export_dir = pm.get_export_dir(project)
        if output:
            out_path = export_dir / output
        else:
            base_name = Path(file).stem
            out_path = export_dir / base_name

        result_path = export_minutes(minutes, out_path, fmt)

        ext = "Markdown" if fmt == "markdown" else "Word"
        console.print(Panel(
            f"格式：{ext}\n路径：{result_path}",
            title="📤 导出成功",
        ))

    except FileNotFoundError as e:
        console.print(f"[bold red]{e}[/]")
        sys.exit(1)
    except ImportError as e:
        console.print(f"[bold red]{e}[/]")
        sys.exit(1)


@cli.command("search")
@click.argument("keyword", default="")
@click.option("--project", "-p", default=None, help="限定项目范围（默认搜索全部）")
@click.option("--date-from", default=None, help="开始日期（YYYY-MM-DD）")
@click.option("--date-to", default=None, help="结束日期（YYYY-MM-DD）")
@click.option("--assignee", "-a", default=None, help="按责任人过滤")
@click.option("--type", "types", multiple=True, help="按类型过滤：议题/要点/风险/待办/发言/重点（可多次使用）")
@click.option("--todo-only", is_flag=True, help="只搜索待办事项")
@click.option("--risk-only", is_flag=True, help="只搜索风险项")
def search_cmd(keyword: str, project: Optional[str], date_from: Optional[str], date_to: Optional[str],
               assignee: Optional[str], types: tuple, todo_only: bool, risk_only: bool):
    """按关键词检索历史纪要（支持多条件过滤）"""
    searcher = Searcher(pm)

    filter_types = list(types) if types else []
    if todo_only:
        filter_types = ["待办"]
    elif risk_only:
        filter_types = ["风险"]

    results = searcher.search(
        keyword=keyword,
        project_name=project,
        date_from=date_from,
        date_to=date_to,
        assignee=assignee,
        types=filter_types if filter_types else None,
    )

    filter_desc = []
    if project:
        filter_desc.append(f"项目: {project}")
    if date_from:
        filter_desc.append(f"从: {date_from}")
    if date_to:
        filter_desc.append(f"至: {date_to}")
    if assignee:
        filter_desc.append(f"责任人: {assignee}")
    if filter_types:
        filter_desc.append(f"类型: {', '.join(filter_types)}")

    header = f"🔍 搜索结果：[bold]'{keyword}'[/]"
    if filter_desc:
        header += f"  [dim]({', '.join(filter_desc)})[/]"

    console.print("")
    console.print(header)
    console.print("=" * 60)

    if not results:
        console.print("[yellow]未找到匹配的内容[/]")
        return

    total_matches = 0
    for result in results:
        header_parts = [result["title"] or "未命名"]
        if result["date"]:
            header_parts.append(f"[dim]{result['date']}[/]")
        header_parts.append(f"[cyan][项目: {result['project']}][/]")

        console.print("")
        console.print(f"📄 {' | '.join(header_parts)}")
        console.print(f"   文件：[dim]{result['file']}[/]")
        if result["speakers"]:
            console.print(f"   参会：[dim]{', '.join(result['speakers'])}[/]")

        for i, match in enumerate(result["matches"], 1):
            type_colors = {
                "议题": "blue", "要点": "green", "风险": "red",
                "待办": "yellow", "发言": "magenta", "重点": "cyan",
                "议题内容": "blue",
            }
            color = type_colors.get(match["type"], "white")
            console.print(f"   [{color}]{i:>2}. [{match['type']}][/{color}] {match['content'][:80]}")
            if match.get("context"):
                ctx = match["context"].replace("\n", " ")
                console.print(f"       [dim]上下文：{ctx[:120]}[/]")
            if match.get("assignee"):
                assignee = match["assignee"] or "❌ 未指定"
                deadline = match.get("deadline", "") or "❌ 未指定"
                console.print(f"       [dim]→ {assignee} | {deadline}[/]")
            if match.get("speaker"):
                console.print(f"       [dim]发言人：{match['speaker']}[/]")

        total_matches += len(result["matches"])

    console.print("")
    console.print(f"共 {len(results)} 个纪要、{total_matches} 条匹配")


@cli.command("merge")
@click.argument("project")
@click.option("--files", "-f", multiple=True, required=True, help="要合并的纪要文件名（可多次使用）")
@click.option("--title", "-t", default=None, help="合并后的标题")
@click.option("--output", "-o", default=None, help="输出文件名")
@click.option("--no-sort", is_flag=True, help="不按日期排序")
@click.option("--no-source", is_flag=True, help="不保留会议来源")
@click.option("--no-smart-merge", is_flag=True, help="关闭智能合并待办（只做简单去重）")
def merge_cmd(project: str, files: tuple, title: Optional[str], output: Optional[str],
              no_sort: bool, no_source: bool, no_smart_merge: bool):
    """合并多场会议纪要（按时间排序，智能合并待办）"""
    try:
        merger = Merger(pm)
        merged = merger.merge_minutes(
            project_name=project,
            filenames=list(files),
            title=title,
            sort_by_date=not no_sort,
            keep_sources=not no_source,
            smart_merge_todos=not no_smart_merge,
        )

        saved = pm.save_minutes(project, merged, output)

        console.print(Panel(
            f"标题：{merged.title}\n"
            f"日期：{merged.date}\n"
            f"参会人：{', '.join(merged.attendees) or '无'}\n"
            f"议题数：{len(merged.agendas)}\n"
            f"待办数：{len(merged.todos)}\n"
            f"发言段：{len(merged.segments)}\n"
            f"来源标记：{'是' if not no_source else '否'}",
            title="🔗 合并完成",
        ))

        if merged.todos and not no_source:
            has_source = any(t.meeting_source for t in merged.todos)
            if has_source:
                console.print("\n[dim]待办事项来源分布：[/]")
                for i, t in enumerate(merged.todos, 1):
                    src = t.meeting_source or "-"
                    console.print(f"  {i:>2}. {t.task[:40]} [dim]→ {src}[/]")

        console.print(f"\n[green]已保存：{saved}[/]")

    except (FileNotFoundError, ValueError) as e:
        console.print(f"[bold red]{e}[/]")
        sys.exit(1)


@cli.command("list")
@click.option("--project", "-p", default=None, help="查看指定项目的文件")
@click.option("--verbose", "-v", is_flag=True, help="显示详细信息（发言人、待办数等）")
def list_cmd(project: Optional[str], verbose: bool):
    """列出项目或文件"""
    if project:
        raw_files = pm.list_raw_files(project)
        processed_files = pm.list_minutes(project)

        if raw_files:
            console.print("[bold]📄 原始转写文件：[/]")
            for rf in raw_files:
                console.print(f"  - {rf}")
        if processed_files:
            console.print("\n[bold]📋 已处理纪要：[/]")
            for pf in processed_files:
                if verbose:
                    try:
                        minutes = pm.load_minutes(project, pf)
                        speakers = minutes.speakers()
                        speakers_str = ", ".join(speakers) if speakers else "无"
                        info = f"[dim]| {len(minutes.segments)}段 | {len(minutes.agendas)}议题 | {len(minutes.todos)}待办 | 发言人: {speakers_str}[/]"
                        console.print(f"  - {pf} {info}")
                    except Exception:
                        console.print(f"  - {pf}")
                else:
                    console.print(f"  - {pf}")
        if not raw_files and not processed_files:
            console.print("[yellow]该项目暂无文件[/]")
    else:
        projects = pm.list_projects()
        if not projects:
            console.print("[yellow]暂无项目，使用 mm init <name> 创建[/]")
        else:
            console.print("[bold]📁 已有项目：[/]")
            for p in projects:
                if verbose:
                    try:
                        raw = len(pm.list_raw_files(p))
                        processed = len(pm.list_minutes(p))
                        console.print(f"  - {p} [dim]({raw} 原始, {processed} 纪要)[/]")
                    except Exception:
                        console.print(f"  - {p}")
                else:
                    console.print(f"  - {p}")


def main():
    cli()


if __name__ == "__main__":
    main()
