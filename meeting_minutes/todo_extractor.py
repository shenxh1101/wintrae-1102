from __future__ import annotations

import re
from typing import List, Optional

from .models import SpeakerSegment, TodoItem, MeetingMinutes

SPEAKER_PREFIX_RE = re.compile(r"^([\u4e00-\u9fff]{2,4}|[A-Za-z]+(?:\s[A-Za-z]+)*)\s*[：:]\s*")

COMMON_SURNAMES = "王李张刘陈杨赵黄周吴徐孙胡朱高林何郭马罗梁宋郑谢韩唐冯于董萧程曹袁邓许傅沈曾彭吕苏卢蒋蔡贾丁魏薛叶阎余潘杜戴夏钟汪田任姜范方石姚谭廖邹熊金陆郝孔白崔康毛邱秦江史顾侯邵孟龙万段雷钱汤尹黎易常武乔贺赖龚文"

ASSIGNEE_PATTERNS = [
    re.compile(r"(?:由|安排|指派|交给|分配给|交由)\s*([\u4e00-\u9fff]{2,4})\s*(?:来?[做处理跟进负责完成执行])"),
    re.compile(r"([\u4e00-\u9fff]{2,4})\s*负责"),
]

DEADLINE_PATTERNS = [
    re.compile(r"(\d{4}年\d{1,2}月\d{1,2}日?)"),
    re.compile(r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})"),
    re.compile(r"(?:截止|期限|deadline)\s*[是为：:]?\s*(\d{1,2}月\d{1,2}日?)"),
    re.compile(r"(\d{1,2}月\d{1,2}日?[之前以内]*)"),
    re.compile(r"(?:下个?|这个?|本)(?:周|星期|月)[一二三四五六七日末]"),
    re.compile(r"(?:本周|下周|本月|下月|月底|月初|周末)[之前以内]*"),
]

TASK_PATTERNS = [
    re.compile(r"(?:需要|务必|请|安排|计划|准备|拟|将)\s*.+"),
    re.compile(r"(?:待办|TODO|Action\s*Item)[：:].+"),
    re.compile(r"(?:跟进|推进|落实|完成|确认|核实|调研|评估|起草|提交|汇报|Review)\s*.+"),
    re.compile(r"[\u4e00-\u9fff]{2,4}\s*负责\s*.+"),
    re.compile(r"[\u4e00-\u9fff]{2,4}[：:]\s*(?:需要|要|得)?(?:去?[做处理跟进完成执行])\s*.+"),
]

PRIORITY_PATTERNS = [
    re.compile(r"(?:紧急|urgent|高优先|P0|P1|重要且紧急)"),
    re.compile(r"(?:重要|important|高优)"),
    re.compile(r"(?:一般|普通|低优先|P2|P3)"),
]

EXCLUDE_PATTERNS = [
    re.compile(r"^还有个?风险"),
    re.compile(r"^总结[一下]"),
    re.compile(r"^还有一件事"),
    re.compile(r"^[上下]?个?(?:周一|周[二三四五六七日末]|月[初中末]|会议)"),
]


def extract_todos(segments: List[SpeakerSegment], raw_text: str = "", project_history: List[MeetingMinutes] = None, current_meeting_title: str = "") -> List[TodoItem]:
    todos = []
    seen_keys = set()

    for seg in segments:
        content = seg.content
        speaker = seg.speaker
        sentences = _split_sentences(content)
        for sentence in sentences:
            sentence = sentence.strip()
            sentence = SPEAKER_PREFIX_RE.sub("", sentence).strip()
            if not sentence or len(sentence) < 4:
                continue

            is_task = any(p.search(sentence) for p in TASK_PATTERNS)
            is_excluded = any(p.search(sentence) for p in EXCLUDE_PATTERNS)
            if not is_task or is_excluded:
                continue

            assignee = _extract_assignee(sentence, speaker)
            deadline = _extract_deadline(sentence)
            priority = _extract_priority(sentence)
            clean_task = _clean_task_text(sentence)

            dedup_key = _make_dedup_key(clean_task, assignee, deadline)
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)

            todo = TodoItem(
                task=clean_task,
                assignee=assignee,
                deadline=deadline,
                source=speaker,
                priority=priority,
            )

            if project_history:
                _apply_history_to_todo(todo, project_history, current_meeting_title)

            todos.append(todo)

    return todos


def _apply_history_to_todo(todo: TodoItem, project_history: List[MeetingMinutes], current_meeting_title: str = ""):
    key = todo.task_key()
    for pm in project_history:
        for pt in pm.todos:
            if pt.task_key() == key:
                if pt.status and pt.status not in ("待办", todo.status):
                    todo.status = pt.status
                if pt.status_updated_at:
                    todo.status_updated_at = pt.status_updated_at
                if pt.assignee and not todo.assignee:
                    todo.assignee = pt.assignee
                if pt.deadline and not todo.deadline:
                    todo.deadline = pt.deadline
                if pt.priority and not todo.priority:
                    todo.priority = pt.priority
                if pt.history:
                    seen_h = {(h.date, h.status) for h in todo.history}
                    for h in pt.history:
                        if (h.date, h.status) not in seen_h:
                            todo.history.append(h)
                            seen_h.add((h.date, h.status))
                existing_as = set(todo.get_all_assignees())
                for a in pt.get_all_assignees():
                    if a and a not in existing_as:
                        todo.assignees.append(a)
                        existing_as.add(a)
                existing_ds = set(todo.get_all_deadlines())
                for d in pt.get_all_deadlines():
                    if d and d not in existing_ds:
                        todo.deadlines.append(d)
                        existing_ds.add(d)
                existing_ss = set(todo.get_all_sources())
                for s in pt.get_all_sources():
                    if s and s not in existing_ss:
                        todo.meeting_sources.append(s)
                        existing_ss.add(s)
                break
    if current_meeting_title and current_meeting_title not in todo.get_all_sources():
        todo.meeting_source = current_meeting_title


def _make_dedup_key(task: str, assignee: str, deadline: str) -> str:
    core = re.sub(r"[，,。.；;！!？?\s]", "", task)
    if assignee:
        core = core.replace(assignee, "")
    if deadline:
        core = core.replace(deadline, "")
    return core[:40]


def _split_sentences(text: str) -> List[str]:
    parts = re.split(r"[。；]", text)
    result = []
    for part in parts:
        sub_parts = re.split(r"[，；]\s*(?=[\u4e00-\u9fff]{2,4}(?:负责|来[做处理跟进完成执行]))", part)
        result.extend(sub_parts)
    return result


def _is_likely_name(text: str) -> bool:
    if len(text) < 2 or len(text) > 4:
        return False
    if text[0] in COMMON_SURNAMES:
        return True
    if re.match(r"^[A-Za-z]+(?:\s[A-Za-z]+)*$", text):
        return True
    return False


def _extract_assignee(sentence: str, context_speaker: str = "") -> str:
    for pattern in ASSIGNEE_PATTERNS:
        match = pattern.search(sentence)
        if match:
            name = match.group(1).strip()
            if _is_likely_name(name):
                return name

    pronoun_patterns = [
        re.compile(r"我负责"),
        re.compile(r"我来[做处理跟进完成执行]"),
        re.compile(r"由我[做处理准备安排完成]"),
        re.compile(r"我[去来]?[做处理跟进完成执行起草提交准备]"),
    ]
    for pp in pronoun_patterns:
        if pp.search(sentence) and context_speaker:
            return context_speaker

    return ""


def _extract_deadline(sentence: str) -> str:
    for pattern in DEADLINE_PATTERNS:
        match = pattern.search(sentence)
        if match:
            if match.lastindex:
                return match.group(1)
            return match.group(0)
    return ""


def _extract_priority(sentence: str) -> str:
    for i, pattern in enumerate(PRIORITY_PATTERNS):
        if pattern.search(sentence):
            return ["紧急", "重要", "一般"][i]
    return ""


def _clean_task_text(sentence: str) -> str:
    sentence = SPEAKER_PREFIX_RE.sub("", sentence)
    sentence = re.sub(r"^(?:嗯|啊|呃|那个|就是说|对吧|然后呢?)[，,]?\s*", "", sentence)
    sentence = sentence.strip("，,。；；")
    return sentence.strip()
