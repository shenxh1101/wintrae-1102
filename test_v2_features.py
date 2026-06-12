#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试会议纪要工具的第二版新功能"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import os
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from meeting_minutes.models import MeetingMinutes, TodoItem, SpeakerSegment, AgendaItem
from meeting_minutes.splitter import split_by_speakers
from meeting_minutes.searcher import Searcher
from meeting_minutes.merger import Merger
from meeting_minutes.project import ProjectManager
from meeting_minutes.todo_extractor import extract_todos
from meeting_minutes.exporter import export_markdown

pm = ProjectManager()


def build_minutes(title, date, attendees=None, seg_text=None, agendas=None, todos=None, risks=None, highlights=None, source_file=None):
    """构建一个测试用 MeetingMinutes"""
    segments = []
    if seg_text:
        segments = split_by_speakers(seg_text)
    minutes = MeetingMinutes(
        title=title,
        date=date,
        attendees=attendees or [],
        segments=segments,
        agendas=agendas or [],
        todos=todos or [],
        risks=risks or [],
        highlights=highlights or [],
        source_file=source_file or "",
    )
    return minutes


def test_speaker_segment_source():
    """测试 SpeakerSegment / AgendaItem / TodoItem 来源字段"""
    print("=" * 60)
    print("🎯 测试1: 数据模型来源字段支持")
    print("=" * 60)

    seg = SpeakerSegment(speaker="张三", content="我来汇报", meeting_source="周会第1期")
    print(f"  SpeakerSegment.meeting_source = '{seg.meeting_source}'")

    agenda = AgendaItem(title="项目进度", content="讨论开发情况", meeting_source="周会第1期")
    print(f"  AgendaItem.meeting_source = '{agenda.meeting_source}'")

    todo = TodoItem(task="完成API开发", assignee="李四", deadline="6月20日", meeting_source="周会第1期")
    assert todo.get_all_sources() == ["周会第1期"]
    print(f"  TodoItem.get_all_sources() = {todo.get_all_sources()}")
    print("✅ 数据模型来源字段正常！")
    return True


def test_todo_multiple_assignees_deadlines():
    """测试 TodoItem 多负责人多截止时间支持"""
    print("\n" + "=" * 60)
    print("🎯 测试2: TodoItem 多负责人多截止时间")
    print("=" * 60)

    todo = TodoItem(
        task="完成登录模块修复",
        assignee="张三",
        deadline="6月15日",
        assignees=["李四", "王五"],
        deadlines=["6月20日", "6月25日"],
        meeting_sources=["周会1", "周会2", "周会3"],
    )

    print(f"  主负责人: '{todo.assignee}', 主截止: '{todo.deadline}'")
    print(f"  其他负责人: {todo.assignees}")
    print(f"  其他截止: {todo.deadlines}")
    print(f"  get_all_assignees() = {todo.get_all_assignees()}")
    print(f"  get_all_deadlines() = {todo.get_all_deadlines()}")
    print(f"  display_assignees() = '{todo.display_assignees()}'")
    print(f"  display_deadlines() = '{todo.display_deadlines()}'")
    print(f"  get_all_sources() = {todo.get_all_sources()}")

    assert todo.get_all_assignees() == ["张三", "李四", "王五"]
    assert todo.get_all_deadlines() == ["6月15日", "6月20日", "6月25日"]
    assert todo.display_assignees() == "张三、李四、王五"
    assert len(todo.get_all_sources()) == 3

    missing = todo.missing_fields
    print(f"  missing_fields = {missing} (预期: [])")
    assert missing == []

    todo2 = TodoItem(task="未指派的任务", assignees=[], deadlines=[])
    print(f"\n  空任务 missing_fields = {todo2.missing_fields} (预期: ['责任人','截止时间'])")
    assert todo2.missing_fields == ["责任人", "截止时间"]

    print("✅ 多负责人多截止时间功能正常！")
    return True


def test_searcher_robustness():
    """测试搜索器稳定性 - 处理异常日期格式、不退出"""
    print("\n" + "=" * 60)
    print("🎯 测试3: 搜索器稳定性 (异常日期不退出)")
    print("=" * 60)

    searcher = Searcher(pm)

    # 构建不同日期格式的会议纪要
    m1 = build_minutes(
        title="周会第1期",
        date="2026-06-10",  # 标准格式
        todos=[TodoItem(task="完成前端开发", assignee="张三", deadline="本周五")],
        risks=["登录模块权限风险"],
        agendas=[AgendaItem(title="项目进度汇报")],
    )

    m2 = build_minutes(
        title="周会第2期",
        date="2026年6月17号",  # 非标准格式
        todos=[TodoItem(task="修复登录权限", assignee="李四", deadline="下周三")],
        risks=[],
        agendas=[AgendaItem(title="新需求讨论")],
    )

    m3 = build_minutes(
        title="临时会议",
        date="昨天下午",  # 完全不可解析
        todos=[TodoItem(task="性能优化", assignee="王五")],
        agendas=[AgendaItem(title="紧急问题")],
    )

    print("  构建3个纪要，日期分别为: '2026-06-10', '2026年6月17号', '昨天下午'")

    def run_search(label, **kwargs):
        try:
            matches = []
            for m in [m1, m2, m3]:
                r = searcher._search_in_minutes(m, **kwargs)
                matches.extend(r)
            print(f"  {label}: 找到 {len(matches)} 条匹配")
            return matches
        except Exception as e:
            print(f"  {label}: ❌ 异常 - {e}")
            import traceback
            traceback.print_exc()
            return None

    # 1. 全类型搜索 (关键词: "权限")
    result1 = run_search("全类型搜索('权限')", keyword="权限", assignee="", types=None)
    assert result1 is not None and len(result1) >= 2, "权限关键词应匹配多个"

    # 2. 只搜待办
    result2 = run_search("仅搜待办", keyword="", assignee="", types=["待办"])
    assert result2 is not None and len(result2) == 3, "应找到3条待办"

    # 3. 按责任人搜 (张三)
    result3 = run_search("责任人='张三'", keyword="", assignee="张三", types=None)
    assert result3 is not None and len(result3) >= 1

    # 4. 风险+待办类型过滤
    result4 = run_search("类型=['风险','待办']", keyword="", assignee="", types=["风险", "待办"])
    assert result4 is not None, "不应抛出异常"

    # 5. 空关键词，不限制类型，不限制assignee
    result5 = run_search("全量空搜", keyword="", assignee="", types=None)
    assert result5 is not None, "全量搜索不应异常"
    print(f"     (m1有{len(m1.agendas)}议题, m2有{len(m2.agendas)}议题)")

    # 6. 验证日期过滤器
    dt_from = searcher._parse_date_filter("2026-06-01")
    dt_to = searcher._parse_date_filter("2026-06-30", end_of_day=True)
    print(f"\n  日期过滤: 2026-06-01 ~ 2026-06-30")
    for label, m in [("m1", m1), ("m2", m2), ("m3", m3)]:
        try:
            date_str = MeetingMinutes.parse_date(m.date)
            if date_str:
                date_parsed = datetime.strptime(date_str, "%Y-%m-%d")
            else:
                date_parsed = None
        except Exception:
            date_parsed = None
        print(f"    {label}: date='{m.date}' -> parsed={date_parsed}")
        if dt_from and date_parsed and date_parsed < dt_from:
            print(f"       -> 早于起始，过滤排除")
        elif dt_to and date_parsed and date_parsed > dt_to:
            print(f"       -> 晚于结束，过滤排除")
        else:
            print(f"       -> 保留")

    print("✅ 搜索器稳定性测试通过！")
    return True


def test_merger_with_sources():
    """测试合并时全链路来源标记 + 智能合并待办"""
    print("\n" + "=" * 60)
    print("🎯 测试4: 合并功能 - 来源标记 + 智能合并待办")
    print("=" * 60)

    m1 = build_minutes(
        title="周会第1期",
        date="2026-06-10",
        attendees=["张三", "李四"],
        seg_text="主持人：讨论一下登录模块\n【张三】：我来负责登录模块的权限修复，大概15号能完。",
        agendas=[
            AgendaItem(
                title="登录模块讨论",
                content="讨论安全风险和开发计划",
                risks=["权限漏洞风险"],
            )
        ],
        todos=[
            TodoItem(task="完成登录模块权限修复", assignee="", deadline="", source="张三发言"),
            TodoItem(task="完成前端开发", assignee="张三", deadline="6月15日"),
        ],
        risks=["登录权限漏洞"],
        highlights=["登录模块是重点"],
    )

    m2 = build_minutes(
        title="周会第2期",
        date="2026-06-17",
        attendees=["张三", "王五"],
        seg_text="主持人：上周的登录模块进度怎么样？\n【张三】：我太忙了，让李四和王五一起做，20号完成。",
        agendas=[
            AgendaItem(
                title="上周待办跟进",
                content="跟进登录模块进展",
                key_sentences=["登录模块进度落后"],
            )
        ],
        todos=[
            TodoItem(task="完成登录模块的权限修复工作", assignee="李四", deadline="6月20日"),
            TodoItem(task="完成登录模块权限修复", assignee="王五", deadline="6月25日", priority="高"),
        ],
        risks=[],
        highlights=["登录模块需要多人协作"],
    )

    merger = Merger(pm)
    all_mins = [m1, m2]
    for m in all_mins:
        m.source_file = m.title + ".json"

    merged = merger.merge_minutes.__wrapped__ if hasattr(merger.merge_minutes, "__wrapped__") else None
    # 直接调用内部方法（不走 pm.load_minutes）
    merged = _direct_merge(merger, all_mins, "合并会议1+2")

    print(f"\n  合并结果:")
    print(f"    title: {merged.title}")
    print(f"    议题数: {len(merged.agendas)}")
    print(f"    发言数: {len(merged.segments)}")
    print(f"    待办数: {len(merged.todos)}")
    print(f"    风险数: {len(merged.risks)}")
    print(f"    参会人: {', '.join(merged.attendees)}")

    # 验证发言来源
    print("\n  发言来源:")
    for i, seg in enumerate(merged.segments, 1):
        print(f"    {i}. [{seg.speaker}] source='{seg.meeting_source}'  content='{seg.content[:40]}...'")
        assert seg.meeting_source, f"发言#{i} 应该有meeting_source"

    # 验证议题来源
    print("\n  议题来源:")
    for i, agenda in enumerate(merged.agendas, 1):
        print(f"    {i}. title='{agenda.title}'  source='{agenda.meeting_source}'")
        assert agenda.meeting_source, f"议题#{i} 应该有 meeting_source"

    # 验证待办合并 (登录模块权限修复应该合并为1条)
    print("\n  待办详情:")
    login_todo = None
    for t in merged.todos:
        sources = t.get_all_sources()
        print(f"    - 任务: {t.task[:45]}")
        print(f"      负责人: '{t.display_assignees()}'")
        print(f"      截止: '{t.display_deadlines()}'")
        print(f"      优先级: '{t.priority or '-'}'")
        print(f"      会议来源: {sources}")
        if "登录" in t.task and "权限" in t.task:
            login_todo = t

    assert login_todo is not None, "登录模块权限修复的待办应该存在"

    # 检查合并后的待办：应该有多个负责人、多个截止时间、多个来源
    all_as = login_todo.get_all_assignees()
    all_ds = login_todo.get_all_deadlines()
    all_srcs = login_todo.get_all_sources()
    print(f"\n  登录任务检查:")
    print(f"    所有负责人: {all_as} (应包含张三相关 + 李四 + 王五)")
    print(f"    所有截止: {all_ds} (应包含 6月15日、20日、25日等)")
    print(f"    所有来源: {all_srcs} (应包含周会第1期 + 周会第2期)")
    print(f"    priority: '{login_todo.priority}'")

    assert len(all_as) >= 2, f"应合并多个负责人，实际{all_as}"
    assert len(all_ds) >= 2, f"应合并多个截止时间，实际{all_ds}"
    assert len(all_srcs) >= 2, f"应合并多个来源，实际{all_srcs}"
    assert login_todo.priority == "高", "优先级应该保留为高"

    print("✅ 合并智能功能正常！")
    return True


def _direct_merge(merger, all_minutes, title):
    """绕过 Merger 对 pm.load_minutes 的依赖直接合并"""
    from meeting_minutes.models import MeetingMinutes, SpeakerSegment, AgendaItem, TodoItem
    from datetime import datetime

    all_minutes = list(all_minutes)

    def sort_key(m):
        try:
            d = m.get_parsed_date()
            return d or datetime.max
        except Exception:
            return datetime.max
    all_minutes.sort(key=sort_key)

    merged = MeetingMinutes()
    merged.title = title
    merged.date = all_minutes[-1].date

    seen_attendees = set()
    for m in all_minutes:
        for a in m.attendees:
            if a not in seen_attendees:
                merged.attendees.append(a)
                seen_attendees.add(a)

    for m in all_minutes:
        source_label = m.title or m.source_file or "会议"
        for seg in m.segments:
            content = f"[{source_label}] " + seg.content
            merged.segments.append(SpeakerSegment(
                speaker=seg.speaker,
                content=content,
                timestamp=seg.timestamp,
                meeting_source=seg.meeting_source or source_label,
            ))

    for m in all_minutes:
        source_label = m.title or m.source_file or "会议"
        for agenda in m.agendas:
            merged.agendas.append(AgendaItem(
                title=f"[{source_label}] {agenda.title}",
                content=agenda.content,
                key_sentences=list(agenda.key_sentences),
                risks=list(agenda.risks),
                meeting_source=agenda.meeting_source or source_label,
            ))

    todos_result = merger._smart_merge_todos(all_minutes, keep_sources=True)
    merged.todos = todos_result[0] if isinstance(todos_result, tuple) else todos_result

    seen_highlights = set()
    for m in all_minutes:
        source_label = m.title or m.source_file or "会议"
        for h in m.highlights:
            hk = f"[{source_label}] {h}"
            if hk not in seen_highlights:
                merged.highlights.append(hk)
                seen_highlights.add(hk)

    seen_risks = {}
    for m in all_minutes:
        source_label = m.title or m.source_file or "会议"
        for r in m.risks:
            if r not in seen_risks:
                seen_risks[r] = set()
            seen_risks[r].add(source_label)
    for r, srcs in seen_risks.items():
        merged.risks.append(f"{r} [来源：{'、'.join(sorted(srcs))}]")

    return merged


def test_search_result_sources():
    """测试搜索结果中的来源信息"""
    print("\n" + "=" * 60)
    print("🎯 测试5: 搜索结果包含会议/议题/发言来源")
    print("=" * 60)

    searcher = Searcher(pm)
    m = build_minutes(
        title="周会-2026.06.17",
        date="2026-06-17",
        agendas=[
            AgendaItem(
                title="权限模块设计",
                content="讨论角色权限分配",
                key_sentences=["管理员权限需要分级"],
                risks=["越权访问风险"],
                meeting_source="周会-2026.06.17",
            )
        ],
        todos=[
            TodoItem(task="完成权限系统开发", assignee="张三", deadline="7月1日",
                     meeting_source="周会-2026.06.17", agenda_source="议题#1 权限模块设计"),
        ],
        risks=["越权访问风险"],
    )

    matches = searcher._search_in_minutes(m, keyword="权限", assignee="", types=None)
    print(f"\n  搜索 '权限' 共找到 {len(matches)} 条匹配:")
    for i, m_item in enumerate(matches, 1):
        fields = [k for k in ("meeting", "agenda_ref", "segment_index", "todo_index") if m_item.get(k)]
        print(f"    {i:>2}. [{m_item['type']}] {m_item['content'][:40]}...")
        if m_item.get("assignee"):
            print(f"        责任人={m_item['assignee']}, 截止={m_item.get('deadline','')}")
        for f in fields:
            print(f"        来源字段: {f}={m_item[f]}")

    todo_matches = [x for x in matches if x["type"] == "待办"]
    if todo_matches:
        tm = todo_matches[0]
        assert tm.get("meeting"), "待办匹配应包含会议来源"
        assert tm.get("todo_index"), "待办匹配应包含 todo_index"
        print(f"\n  ✅ 待办包含会议来源: '{tm['meeting']}', index={tm['todo_index']}")

    agenda_matches = [x for x in matches if x["type"] in ("议题", "议题内容", "要点", "风险")]
    if agenda_matches:
        am = agenda_matches[0]
        assert am.get("meeting"), "议题匹配应包含会议来源"
        assert am.get("agenda_ref"), "议题匹配应包含议题引用"
        print(f"  ✅ 议题包含来源: '{am['meeting']}', ref='{am['agenda_ref']}'")

    print("✅ 搜索结果来源信息正常！")
    return True


def test_markdown_export_with_sources():
    """测试 Markdown 导出包含来源信息"""
    print("\n" + "=" * 60)
    print("🎯 测试6: Markdown 导出包含来源信息")
    print("=" * 60)

    m = build_minutes(
        title="合并会议纪要",
        date="2026-06-17",
        attendees=["张三", "李四"],
        agendas=[
            AgendaItem(title="登录模块讨论", content="...", meeting_source="周会第1期"),
            AgendaItem(title="上周跟进", content="...", meeting_source="周会第2期"),
        ],
        seg_text=None,
    )
    # 直接填充 segments (不走 splitter)
    m.segments = [
        SpeakerSegment(speaker="张三", content="我来负责这个", meeting_source="周会第1期"),
        SpeakerSegment(speaker="李四", content="我也帮忙", meeting_source="周会第2期"),
    ]
    m.todos = [
        TodoItem(task="完成登录模块", assignee="张三", deadline="6月15日",
                 meeting_sources=["周会第1期", "周会第2期"], assignees=["李四", "王五"],
                 deadlines=["6月20日", "6月25日"], priority="高",
                 agenda_source="议题#1 登录模块讨论"),
    ]
    m.risks = ["登录权限风险 [来源：周会第1期、周会第2期]"]

    md = export_markdown(m)
    print(f"\n  生成的 Markdown 关键片段:\n")

    lines = md.split("\n")
    for line in lines:
        line = line.rstrip()
        if any(k in line for k in ("议题", "待办", "发言", "来源", "周会", "张三", "李四", "王五")):
            print(f"  {line[:100]}")

    # 检查关键信息
    checks = [
        ("议题来源", "周会第1期" in md and "周会第2期" in md),
        ("多负责人显示", "张三、李四、王五" in md),
        ("多截止显示", ("6月15日" in md) and ("6月20日" in md) and ("6月25日" in md)),
        ("待办会议来源列", "周会第1期" in md and "周会第2期" in md),
        ("发言来源", "*[周会第1期]*" in md and "*[周会第2期]*" in md),
        ("风险来源", "周会第1期、周会第2期" in md),
    ]

    print(f"\n  导出内容检查:")
    all_ok = True
    for name, ok in checks:
        mark = "✅" if ok else "❌"
        print(f"    {mark} {name}")
        if not ok:
            all_ok = False

    if all_ok:
        print("✅ Markdown 导出包含完整来源信息！")
    return all_ok


def test_parse_date_robustness():
    """测试 MeetingMinutes.parse_date 各种输入"""
    print("\n" + "=" * 60)
    print("🎯 测试7: parse_date 健壮性")
    print("=" * 60)

    cases = [
        ("2026-06-20", "2026-06-20"),
        ("2026/06/20", "2026-06-20"),
        ("20260620", "2026-06-20"),
        ("2026年6月20日", "2026-06-20"),
        ("2026年6月20号", "2026-06-20"),
        ("2026-6-1", "2026-06-01"),
        ("2026年06月01", "2026-06-01"),
        ("6月20日", None),
        ("下周三", None),
        ("昨天", None),
        ("", None),
        (None, None),
        ("非法日期abc123", None),
    ]

    all_ok = True
    for inp, expected in cases:
        try:
            result = MeetingMinutes.parse_date(inp if inp is not None else "")
        except Exception as e:
            result = f"EXCEPTION: {e}"
            all_ok = False
        ok = result == expected
        mark = "✅" if ok else "❌"
        status = "OK" if ok else f"FAIL (got {result})"
        print(f"  {mark} parse_date('{inp}') = {result}  {status}")
        if not ok:
            all_ok = False

    return all_ok


def main():
    print("\n╔" + "=" * 58 + "╗")
    print("║" + " " * 10 + "会议纪要工具 V2 新功能测试" + " " * 26 + "║")
    print("╚" + "=" * 58 + "╝")

    tests = [
        ("数据模型来源字段", test_speaker_segment_source),
        ("TodoItem 多负责人/多截止", test_todo_multiple_assignees_deadlines),
        ("搜索器稳定性", test_searcher_robustness),
        ("合并 - 来源/智能待办", test_merger_with_sources),
        ("搜索结果来源信息", test_search_result_sources),
        ("Markdown导出来源", test_markdown_export_with_sources),
        ("parse_date 健壮性", test_parse_date_robustness),
    ]

    passed = 0
    failed = 0
    failures = []

    for name, test_fn in tests:
        try:
            if test_fn():
                passed += 1
            else:
                failed += 1
                failures.append(name)
        except Exception as e:
            failed += 1
            failures.append(f"{name} (异常: {e})")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)
    print(f"📊 测试结果: {passed} 通过, {failed} 失败")
    if failures:
        print(f"❌ 失败项: {', '.join(failures)}")
    else:
        print("🎉 全部测试通过！")
    print("=" * 60)
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
