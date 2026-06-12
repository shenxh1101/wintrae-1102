from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

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
@click.version_option(version="1.0.0", prog_name="meeting-minutes")
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
def import_file(project: str, file: str, name: Optional[str]):
    """导入转写文本到项目"""
    try:
        dest = pm.import_transcript(project, file, name)
        console.print(f"[green]✅ 已导入到：{dest}[/]")
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
        console.print(Panel(
            f"原始字数：{len(text)}\n"
            f"清洗后字数：{len(cleaned)}\n"
            f"减少：{len(text) - len(cleaned)} 字符\n"
            f"识别发言段：{len(cleaned_segments)} 段",
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
    """按发言人分段"""
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

        table = Table(title="📝 发言分段结果")
        table.add_column("#", style="dim", width=4)
        table.add_column("发言人", style="cyan", width=12)
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

        table = Table(title="✅ 待办事项")
        table.add_column("#", style="dim", width=4)
        table.add_column("任务", width=35)
        table.add_column("责任人", style="cyan", width=10)
        table.add_column("截止时间", style="yellow", width=14)
        table.add_column("优先级", style="red", width=8)
        table.add_column("来源", style="dim", width=10)

        for i, t in enumerate(todos, 1):
            assignee = t.assignee or "[red]❌ 缺失[/]"
            deadline = t.deadline or "[red]❌ 缺失[/]"
            priority = t.priority or "-"
            source = t.source or "-"
            table.add_row(str(i), t.task[:50], assignee, deadline, priority, source)

        console.print(table)

        checker = Checker()
        issues = checker.check_todos(todos)
        if issues:
            console.print(f"\n[yellow]⚠️ {len(issues)} 项待办缺少责任人或截止时间[/]")

        console.print(f"\n[green]已更新：{file}[/]")

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
@click.argument("keyword")
@click.option("--project", "-p", default=None, help="限定项目范围（默认搜索全部）")
def search_cmd(keyword: str, project: Optional[str]):
    """按关键词检索历史纪要"""
    searcher = Searcher(pm)

    if project:
        results = searcher.search_in_project(project, keyword)
    else:
        results = searcher.search_across_projects(keyword)

    console.print(searcher.format_search_results(results, keyword))


@cli.command("merge")
@click.argument("project")
@click.option("--files", "-f", multiple=True, required=True, help="要合并的纪要文件名（可多次使用）")
@click.option("--title", "-t", default=None, help="合并后的标题")
@click.option("--output", "-o", default=None, help="输出文件名")
@click.option("--no-dedup", is_flag=True, help="不去重待办事项")
def merge_cmd(project: str, files: tuple, title: Optional[str], output: Optional[str], no_dedup: bool):
    """合并多场会议纪要"""
    try:
        merger = Merger(pm)
        merged = merger.merge_minutes(
            project_name=project,
            filenames=list(files),
            title=title,
            deduplicate=not no_dedup,
        )

        saved = pm.save_minutes(project, merged, output)

        console.print(Panel(
            f"标题：{merged.title}\n"
            f"参会人：{', '.join(merged.attendees)}\n"
            f"议题数：{len(merged.agendas)}\n"
            f"待办数：{len(merged.todos)}\n"
            f"发言段：{len(merged.segments)}",
            title="🔗 合并完成",
        ))
        console.print(f"[green]已保存：{saved}[/]")

    except (FileNotFoundError, ValueError) as e:
        console.print(f"[bold red]{e}[/]")
        sys.exit(1)


@cli.command("list")
@click.option("--project", "-p", default=None, help="查看指定项目的文件")
def list_cmd(project: Optional[str]):
    """列出项目或文件"""
    if project:
        raw_files = pm.list_raw_files(project)
        processed_files = pm.list_minutes(project)

        if raw_files:
            console.print("[bold]原始转写文件：[/]")
            for rf in raw_files:
                console.print(f"  📄 {rf}")
        if processed_files:
            console.print("[bold]已处理纪要：[/]")
            for pf in processed_files:
                console.print(f"  📋 {pf}")
        if not raw_files and not processed_files:
            console.print("[yellow]该项目暂无文件[/]")
    else:
        projects = pm.list_projects()
        if not projects:
            console.print("[yellow]暂无项目，使用 mm init <name> 创建[/]")
        else:
            console.print("[bold]已有项目：[/]")
            for p in projects:
                console.print(f"  📁 {p}")


def main():
    cli()


if __name__ == "__main__":
    main()
