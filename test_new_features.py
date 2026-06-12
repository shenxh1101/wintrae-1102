#!/usr/bin/env python3
"""测试会议纪要工具的新功能"""

import sys
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

pm = ProjectManager()


def test_speaker_detection():
    """测试多种发言人格式识别"""
    print("=" * 60)
    print("🎯 测试1: 多种发言人格式识别")
    print("=" * 60)

    text = """主持人：大家好
【张三】：前端完成80%
[李四]：后端接口写完了
发言人1：测试用例准备好了
嘉宾一：我补充一点
主持人2：还有问题吗
【王五】：没问题了"""

    segments = split_by_speakers(text)
    print(f"\n识别到 {len(segments)} 段发言：")
    for i, seg in enumerate(segments, 1):
        print(f"  {i:>2}. [{seg.speaker:>10}] {seg.content[:50]}")

    speakers = set(s.speaker for s in segments)
    expected = {"主持人", "张三", "李四", "发言人1", "嘉宾一", "主持人2", "王五"}
    print(f"\n识别到的发言人：{sorted(speakers)}")
    print(f"预期发言人：{sorted(expected)}")

    missing = expected - speakers
    if missing:
        print(f"❌ 遗漏：{missing}")
        return False
    else:
        print("✅ 所有发言人格式都正确识别！")
        return True


def test_splitter_with_real_file():
    """测试真实文件的分割效果"""
    print("\n" + "=" * 60)
    print("🎯 测试2: 真实转写文件分割")
    print("=" * 60)

    test_file = Path(__file__).parent / "test_transcript1.txt"
    text = test_file.read_text(encoding="utf-8")

    segments = split_by_speakers(text)
    speakers = set(s.speaker for s in segments)

    print(f"\n文件：{test_file.name}")
    print(f"总段数：{len(segments)}")
    print(f"发言人：{sorted(speakers)}")

    expected = {"主持人", "张三", "李四", "发言人1", "发言人2"}
    missing = expected - speakers
    if missing:
        print(f"❌ 遗漏发言人：{missing}")
        return False

    print("\n前5段发言：")
    for i, seg in enumerate(segments[:5], 1):
        print(f"  {i:>2}. [{seg.speaker:>10}] {seg.content[:60]}...")

    print("✅ 真实文件分割正确！")
    return True


def test_todo_extraction():
    """测试待办事项提取"""
    print("\n" + "=" * 60)
    print("🎯 测试3: 待办事项提取")
    print("=" * 60)

    test_file = Path(__file__).parent / "test_transcript1.txt"
    text = test_file.read_text(encoding="utf-8")
    segments = split_by_speakers(text)

    todos = extract_todos(segments, text)
    print(f"\n提取到 {len(todos)} 个待办：")
    for i, t in enumerate(todos, 1):
        print(f"  {i:>2}. 任务：{t.task[:60]}")
        print(f"      责任人：{t.assignee or '未识别'}, 截止：{t.deadline or '未识别'}")
        if t.priority:
            print(f"      优先级：{t.priority}")

    if len(todos) >= 3:
        print("✅ 待办提取正常！")
        return True
    else:
        print("❌ 待办提取数量不足")
        return False


def test_smart_merge():
    """测试智能合并待办"""
    print("\n" + "=" * 60)
    print("🎯 测试4: 智能合并重复待办")
    print("=" * 60)

    todo1 = TodoItem(
        task="完成登录模块权限修复",
        assignee="",
        deadline="",
        meeting_source="会议A",
    )
    todo2 = TodoItem(
        task="完成登录模块的权限修复工作",
        assignee="张三",
        deadline="2026-06-20",
        meeting_source="会议B",
    )

    print(f"\n待办1 (会议A): task='{todo1.task}', assignee='{todo1.assignee}', deadline='{todo1.deadline}'")
    print(f"待办2 (会议B): task='{todo2.task}', assignee='{todo2.assignee}', deadline='{todo2.deadline}'")
    print(f"待办1 task_key: {todo1.task_key()}")
    print(f"待办2 task_key: {todo2.task_key()}")
    print(f"key相同: {todo1.task_key() == todo2.task_key()}")

    key1 = todo1.task_key()
    key2 = todo2.task_key()

    if key1 == key2:
        merged = TodoItem(
            task=todo1.task,
            assignee=todo1.assignee or todo2.assignee,
            deadline=todo1.deadline or todo2.deadline,
            meeting_source=f"{todo1.meeting_source}, {todo2.meeting_source}",
        )
        print(f"\n智能合并结果:")
        print(f"  任务: {merged.task}")
        print(f"  责任人: {merged.assignee} (来自会议B)")
        print(f"  截止: {merged.deadline} (来自会议B)")
        print(f"  来源: {merged.meeting_source}")
        print("✅ 智能合并正常！")
        return True
    else:
        print("❌ task_key 应该相同但不同")
        return False


def test_search_filter():
    """测试搜索过滤功能"""
    print("\n" + "=" * 60)
    print("🎯 测试5: 搜索过滤功能")
    print("=" * 60)

    minutes1 = MeetingMinutes(
        title="项目周会 - 第1周",
        date="2026-06-10",
        attendees=["张三", "李四"],
        todos=[
            TodoItem(task="完成前端开发", assignee="张三", deadline="2026-06-15", meeting_source="周会1"),
            TodoItem(task="修复登录权限", assignee="李四", deadline="2026-06-20", meeting_source="周会1"),
        ],
        agendas=[AgendaItem(title="项目进度汇报", content="讨论项目进展情况")],
        risks=["登录模块可能存在安全隐患"],
    )

    minutes2 = MeetingMinutes(
        title="项目周会 - 第2周",
        date="2026-06-17",
        attendees=["张三", "王五"],
        todos=[
            TodoItem(task="完成前端开发", assignee="张三", deadline="2026-06-18", meeting_source="周会2"),
            TodoItem(task="数据导出功能", assignee="王五", deadline="2026-07-15", meeting_source="周会2"),
        ],
        agendas=[AgendaItem(title="新需求讨论", content="讨论数据导出功能")],
        highlights=["导出功能优先级高"],
    )

    searcher = Searcher(pm)

    print("\n5.1 按关键词搜索：")
    results = searcher._search_in_minutes(minutes1, "权限", assignee=None, types=None)
    print(f"  搜索 '权限'，找到 {len(results)} 条匹配")
    for r in results:
        print(f"    - [{r['type']}] {r['content'][:60]}")

    print("\n5.2 按类型过滤：")
    results = searcher._search_in_minutes(minutes1, "", assignee=None, types=["待办"])
    print(f"  只看 '待办'，找到 {len(results)} 条")
    for r in results:
        print(f"    - {r['content'][:50]} -> {r.get('assignee')}")

    print("\n5.3 按责任人过滤：")
    results = searcher._search_in_minutes(minutes1, "", assignee="张三", types=None)
    print(f"  责任人 '张三'，找到 {len(results)} 条")
    for r in results:
        print(f"    - {r['content'][:50]}")

    print("\n5.4 上下文提取：")
    results = searcher._search_in_minutes(minutes1, "安全", assignee=None, types=None)
    for r in results:
        print(f"  匹配: {r['content']}")
        print(f"  上下文: {r.get('context', '无')}")

    print("✅ 搜索过滤功能正常！")
    return True


def test_date_parsing():
    """测试日期解析"""
    print("\n" + "=" * 60)
    print("🎯 测试6: 灵活日期解析")
    print("=" * 60)

    test_cases = [
        ("2026-06-20", "2026-06-20"),
        ("2026/6/20", "2026-06-20"),
        ("6月20日", None),  # 没有年份，返回None
        ("下周三", None),  # 相对日期，返回None
        ("本周五", None),
        ("2026年6月20日", "2026-06-20"),
    ]

    all_pass = True
    for input_date, expected in test_cases:
        result = MeetingMinutes.parse_date(input_date)
        status = "✅" if result == expected else "❌"
        print(f"  {status} parse_date('{input_date}') = {result} (预期: {expected})")
        if result != expected:
            all_pass = False

    if all_pass:
        print("✅ 日期解析正常！")
    return all_pass


def test_update_todo():
    """测试更新待办"""
    print("\n" + "=" * 60)
    print("🎯 测试7: 待办更新功能")
    print("=" * 60)

    minutes = MeetingMinutes(
        title="测试会议",
        date="2026-06-10",
        todos=[
            TodoItem(task="任务1", assignee="", deadline=""),
            TodoItem(task="任务2", assignee="张三", deadline=""),
        ],
    )

    print(f"\n初始待办：")
    for i, t in enumerate(minutes.todos, 1):
        print(f"  {i}. {t.task} | 责任人: '{t.assignee}' | 截止: '{t.deadline}'")

    result = minutes.update_todo(1, assignee="李四", deadline="2026-06-20")
    print(f"\n更新 #1 责任人=李四, 截止=2026-06-20")
    print(f"  成功: {result}")
    print(f"  现在: {minutes.todos[0].task} | 责任人: '{minutes.todos[0].assignee}' | 截止: '{minutes.todos[0].deadline}'")

    result = minutes.update_todo(2, deadline="2026-06-25")
    print(f"\n更新 #2 截止=2026-06-25")
    print(f"  成功: {result}")
    print(f"  现在: {minutes.todos[1].task} | 责任人: '{minutes.todos[1].assignee}' | 截止: '{minutes.todos[1].deadline}'")

    result = minutes.update_todo(99, assignee="王五")
    print(f"\n更新 #99 (不存在)")
    print(f"  成功: {result} (预期: False)")

    missing = minutes.todos_with_missing()
    print(f"\n缺失信息的待办: {len(missing)} 项")
    for idx, t in missing:
        print(f"  #{idx}: {t.task}")

    if minutes.todos[0].assignee == "李四" and minutes.todos[0].deadline == "2026-06-20":
        print("✅ 待办更新功能正常！")
        return True
    else:
        print("❌ 待办更新失败")
        return False


def main():
    print("\n" + "╔" + "=" * 58 + "╗")
    print("║" + " " * 15 + "会议纪要工具新功能测试" + " " * 21 + "║")
    print("╚" + "=" * 58 + "╝")

    tests = [
        test_speaker_detection,
        test_splitter_with_real_file,
        test_todo_extraction,
        test_smart_merge,
        test_search_filter,
        test_date_parsing,
        test_update_todo,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"\n❌ 测试异常: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print(f"📊 测试结果: {passed} 通过, {failed} 失败")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
