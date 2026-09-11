#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
baimiao_lint.py — 中文白描成稿启发式体检

用法:
    python3 baimiao_lint.py 文稿.txt
    cat 文稿.txt | python3 baimiao_lint.py
    python3 baimiao_lint.py 文稿.txt --json

只输出指标与修改线索，不自动改稿；阈值为写作训练经验值，
文体不同可浮动，脚本不替代人工判断。仅依赖标准库。
"""

import sys
import re
import json
import statistics

HAN = re.compile(r"[\u4e00-\u9fff]")

# 程度副词（通胀信号）
DEGREE_WORDS = [
    "非常", "极其", "极为", "十分", "格外", "分外", "尤其", "尤为",
    "特别", "相当", "颇为", "甚是", "无比", "异常", "大为", "大幅",
    "极大", "高度", "深度", "显著", "明显", "强烈", "充分", "足足",
    "空前", "前所未有",
]

# 抽象情绪 / 评价词（直给信号）
EMOTION_WORDS = [
    "焦虑", "悲伤", "悲哀", "愤怒", "气愤", "开心", "快乐", "高兴",
    "痛苦", "绝望", "崩溃", "震撼", "感动", "激动", "失落", "沮丧",
    "惆怅", "落寞", "孤独", "寂寞", "幸福", "美好", "温馨", "温暖",
    "伟大", "优秀", "精彩", "出色", "卓越", "杰出", "荒唐", "荒谬",
    "可笑", "可耻", "可恶", "卑鄙", "高尚", "丑陋", "美丽", "漂亮",
    "讨厌", "喜欢", "喜爱", "憎恶", "自豪", "骄傲", "委屈", "心酸",
    "无奈", "尴尬", "窘迫",
]

# 套话 / AI腔 / 公文腔
CLICHE_WORDS = [
    "综上所述", "总而言之", "总的来说", "众所周知", "值得一提的是",
    "不难看出", "由此可见", "与此同时", "在这样的背景下", "在这个",
    "随着", "不断发展", "日新月异", "应运而生", "赋能", "抓手",
    "闭环", "沉淀", "护城河", "生态位", "底层逻辑", "顶层设计",
    "组合拳", "发力", "聚力", "凝心聚力", "保驾护航", "添砖加瓦",
    "不可或缺", "至关重要", "举足轻重", "深远意义", "重要意义",
    "具有重要", "具有重大",
]

# 发令语开头
STARTER_WORDS = ["先说", "先看", "先讲", "我们来看", "咱们来看", "接下来让我们", "下面我们"]

# 比喻标记
METAPHOR_WORDS = ["仿佛", "宛如", "犹如", "好像", "似的", "一般", "好比", "恍若"]

# 最高级 / 绝对化（用户硬约束）
ABSOLUTE_WORDS = ["最", "绝对", "永远", "从不", "无一例外", "百分之百", "史上", "世界之最", "没有之一"]

SENT_SPLIT = re.compile(r"[。！？!?；;\n]+")
NON_HAN = re.compile(r"[^\u4e00-\u9fff]+")


def count_hans(text: str) -> int:
    return len(HAN.findall(text))


def find_hits(text: str, words):
    hits = {}
    for w in words:
        c = text.count(w)
        if c:
            hits[w] = c
    return hits


def split_sentences(text: str):
    raw = [s.strip() for s in SENT_SPLIT.split(text) if s.strip()]
    out = []
    for s in raw:
        n = count_hans(s)
        if n > 0:
            out.append((s, n))
    return out


def four_char_groups(text: str):
    """按非汉字切分，长度恰为四的独立汉字段，粗估四字格密度。"""
    groups = [g for g in NON_HAN.split(text) if len(g) == 4]
    return groups


def lint(text: str):
    total = count_hans(text)
    sents = split_sentences(text)
    lengths = [n for _, n in sents]
    n_sent = len(lengths)

    report = {"总汉字数": total, "有效句数": n_sent}
    if total == 0 or n_sent == 0:
        report["错误"] = "未检测到有效中文内容"
        return report

    avg = statistics.mean(lengths)
    stdev = statistics.pstdev(lengths) if n_sent > 1 else 0.0
    short = sum(1 for n in lengths if n <= 10)
    long_ = sum(1 for n in lengths if n >= 40)
    report["句长"] = {
        "平均句长": round(avg, 1),
        "句长标准差": round(stdev, 1),
        "短句(<=10字)占比": f"{short / n_sent:.0%}",
        "长句(>=40字)数量": long_,
        "最长句字数": max(lengths),
        "最短句字数": min(lengths),
    }

    # 等长句连排：连续三句字数差都在 5 以内
    mono_runs = []
    run = [lengths[0]]
    for n in lengths[1:]:
        if abs(n - run[-1]) <= 5:
            run.append(n)
        else:
            if len(run) >= 3:
                mono_runs.append(len(run))
            run = [n]
    if len(run) >= 3:
        mono_runs.append(len(run))

    de_count = sum(text.count(w) for w in ["的", "地", "得"])
    four = four_char_groups(text)
    metaphor_hits = find_hits(text, METAPHOR_WORDS)
    absolute_hits = find_hits(text, ABSOLUTE_WORDS)

    def per1k(hits):
        return round(sum(hits.values()) * 1000 / total, 1)

    report["用词密度(每千字)"] = {
        "的地得_每百字": round(de_count * 100 / total, 2),
        "程度副词": per1k(find_hits(text, DEGREE_WORDS)),
        "抽象情绪评价词": per1k(find_hits(text, EMOTION_WORDS)),
        "比喻标记": per1k(metaphor_hits),
        "独立四字组_占比": f"{len(''.join(four)) / total:.1%}",
    }

    report["命中明细"] = {
        "程度副词": find_hits(text, DEGREE_WORDS),
        "抽象情绪评价词": find_hits(text, EMOTION_WORDS),
        "套话公文腔": find_hits(text, CLICHE_WORDS),
        "比喻标记": metaphor_hits,
        "绝对化表述": absolute_hits,
    }

    starter_hits = []
    for s, _ in sents:
        for w in STARTER_WORDS:
            if s.startswith(w):
                starter_hits.append(s[:20])
                break
    report["发令语开头句"] = starter_hits
    report["等长句连排段数"] = mono_runs

    advice = []
    if avg > 30:
        advice.append("平均句长偏长，考虑在动作与结论处拆出短句。")
    if short / n_sent < 0.15:
        advice.append("短句占比偏低，节奏可能发闷，补若干十字以内短句。")
    if long_:
        advice.append(f"存在 {long_} 句四十字以上长句，检查换气点。")
    if mono_runs:
        advice.append(f"出现 {len(mono_runs)} 处连续三句以上等长，重排长短句。")
    if de_count * 100 / total > 8:
        advice.append("“的地得”每百字超过八个，排查长定语链，能拆则拆。")
    if per1k(find_hits(text, DEGREE_WORDS)) > 8:
        advice.append("程度副词偏密，逐个验证删除后是否损失语义。")
    if per1k(find_hits(text, EMOTION_WORDS)) > 10:
        advice.append("抽象情绪/评价词偏多，转为动作、神态、物件或事实。")
    if report["命中明细"]["套话公文腔"]:
        advice.append("命中套话词表，逐个人工判断：删、换具体事实，或保留并说明理由。")
    if absolute_hits:
        advice.append("出现绝对化表述，核对是否有依据，无依据则降级表述。")
    if starter_hits:
        advice.append("存在发令语开头句，改为直接进入对象。")
    if not advice:
        advice.append("量化指标未见明显异常，仍需人工核对细节功能与传输保真度。")
    report["修改线索"] = advice
    return report


def render(report) -> str:
    lines = ["== 白描成稿体检 =="]
    for k in ("总汉字数", "有效句数"):
        if k in report:
            lines.append(f"{k}: {report[k]}")
    if "句长" in report:
        lines.append("\n[句长节奏]")
        for k, v in report["句长"].items():
            lines.append(f"  {k}: {v}")
    if "用词密度(每千字)" in report:
        lines.append("\n[用词密度]")
        for k, v in report["用词密度(每千字)"].items():
            lines.append(f"  {k}: {v}")
    lines.append("\n[命中明细]")
    for cat, hits in report["命中明细"].items():
        if hits:
            detail = "，".join(f"{w}×{c}" for w, c in hits.items())
            lines.append(f"  {cat}: {detail}")
        else:
            lines.append(f"  {cat}: 无")
    if report.get("发令语开头句"):
        lines.append("\n[发令语开头]")
        for s in report["发令语开头句"]:
            lines.append(f"  {s}……")
    if report.get("等长句连排段数"):
        lines.append(f"\n[等长句连排] 共 {len(report['等长句连排段数'])} 处")
    lines.append("\n[修改线索]")
    for i, a in enumerate(report["修改线索"], 1):
        lines.append(f"  {i}. {a}")
    return "\n".join(lines)


def main():
    args = sys.argv[1:]
    as_json = "--json" in args
    args = [a for a in args if a != "--json"]

    if args:
        with open(args[0], "r", encoding="utf-8") as f:
            text = f.read()
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        print(__doc__)
        sys.exit(1)

    report = lint(text)
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render(report))


if __name__ == "__main__":
    main()
