"""
================================================================================
文件作用：随机分配 —— 决定每个医生按什么顺序做题
================================================================================

为什么要随机：如果所有人都按同样的顺序做 8 道题，会产生「顺序效应」——
越到后面医生越熟练、也越疲劳，第 8 题的表现天然和第 1 题不同。这种系统性
偏差会混进结果里，让你分不清"这道题难"和"这道题排在最后"。

解决办法：准备 4 套不同的顺序，每个医生随机抽一套。这样顺序带来的影响
在人群中被打散、互相抵消。

--------------------------------------------------------------------------------
本文件的代码块：
--------------------------------------------------------------------------------
  第 1 块  assign_condition()        V3 的分组函数（V4 已停用，保留备查）
  第 2 块  pick_order_template_id()  ★ 从 4 套顺序里随机抽一套
================================================================================
"""

from __future__ import annotations

import random
from typing import Iterable


# ── 第 1 块：V3 的实验分组（已停用）────────────────────────────────────────
def assign_condition(rng: random.Random | None = None) -> str:
    """V3 random plain/guardrail assignment.

    Deprecated in V4 (single-condition study). Kept for archival / replay
    of V3 sessions and for tests that still exercise the V3 contract.
    The V4 session creator wires `condition="single"` directly and does
    not call this function.

    ★ 大白话：V3 版本把医生五五开随机分成两组，一组能看到"风险提示面板"，
    一组看不到，用来比较有没有提示对判断的影响。

    V4 取消了这个设计（所有人看到的界面完全一样），所以这个函数
    **已经没有任何地方调用了**。留着是为了两件事：
      1. 万一要重放/复核 V3 时代收集的那批数据
      2. 还有测试在验证 V3 的行为契约

    ★ 这属于"有意保留的死代码"，不要顺手删掉。
    """
    # rng 参数是为了让测试能传一个固定种子的随机数生成器进来，
    # 这样测试结果可复现。正常运行时不传，用 Python 全局的 random。
    r = rng or random
    # random() 返回 0.0~1.0 之间的小数，小于 0.5 的概率正好是一半。
    return "plain" if r.random() < 0.5 else "guardrail"


# ── 第 2 块：抽题目顺序 ★ ──────────────────────────────────────────────────
def pick_order_template_id(
    template_ids: Iterable[int], rng: random.Random | None = None
) -> int:
    """从若干套顺序模板里随机抽一套，返回它的编号。

    每个医生建档时调用一次（见 api/session.py）。

    参数 template_ids 写成 Iterable（可迭代对象）而不是 list，
    是为了调用方传列表、元组、生成器都行，更灵活。
    """
    # 先转成列表。因为如果传进来的是生成器，它只能遍历一次——
    # 下面既要判断空、又要抽取，不转成列表第二次就取不到东西了。
    ids = list(template_ids)
    if not ids:
        # 一套模板都没有 = 启动时的灌数据没跑成功。
        # 这里明确报错，而不是返回一个假的编号让问题往后蔓延。
        raise ValueError("No order templates available")
    r = rng or random
    # choice() 从列表里等概率随机挑一个。
    # ★ 用等概率而不是"轮流分配"，是随机对照实验的标准做法：
    #   轮流分配的话，知道前一个人分到什么就能推出下一个人分到什么。
    return r.choice(ids)
