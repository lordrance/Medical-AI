"""
================================================================================
文件作用：AI 调用的「记账本」—— 每次调 AI 都要在这里记一笔
================================================================================

★ 一条铁律：**每一次调用 AI 都必须经过这里记一笔，成功要记，失败也要记。**

只在成功时记账是曾经修过的一个真 bug（commit bc933f9）。当时的写法是
"调用成功了就记一笔"，结果所有失败的调用一条记录都没有——而排查问题时
最需要看的恰恰就是失败的那些。

为什么这条规矩重要
------------------
  1. 研究可复现性
     审稿人问"你论文里这段总结是怎么生成的"，你得拿得出当时用的
     提示词原文、模型名字、以及模型返回的原始内容。这些全在这张表里。

  2. 排查和成本
     调了多少次、失败率多少、每次多慢、烧了多少 token。

★ 重要背景：V4 的**医生端完全不调用 AI**（题目文本是写死在 cases.json 里的，
  见 api/case.py 开头的说明）。所以 llm_calls 这张表在生产库里是 0 行。
  只有你在管理后台点「生成研究总结」时才会写入。

--------------------------------------------------------------------------------
本文件的代码块：
--------------------------------------------------------------------------------
  第 1 块  record_llm_call()   唯一的一个函数：往账本里写一行
================================================================================
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LLMCall


# ── 第 1 块：记一笔账 ──────────────────────────────────────────────────────
async def record_llm_call(
    db: AsyncSession,
    # ★ 这个单独的星号是 Python 的语法：它后面的所有参数都**必须写名字**，
    #   不能靠位置传。也就是调用时必须写成
    #       record_llm_call(db, purpose="...", provider="...", model="...")
    #   而不能写成
    #       record_llm_call(db, "...", "...", "...")
    #   参数有 9 个且好几个都是字符串，靠位置传极容易传错顺序而毫无察觉
    #   （把 model 传进 provider 里，程序照跑，数据全错）。
    *,
    purpose: str,                  # 干什么用的，如 "cohort_summary"
    provider: str,                 # 哪家供应商，如 "deepseek"
    model: str,                    # 哪个模型
    prompt_text: str,              # ★ 完整的提示词原文
    response_text: str,            # ★ 模型返回的原始内容
    prompt_tokens: int | None,     # 输入消耗了多少 token（算钱用）
    completion_tokens: int | None, # 输出消耗了多少
    latency_ms: int,               # 这次调用花了多少毫秒
    error: str | None = None,      # ★ 失败时把错误信息填这里，照样要记一笔
) -> None:
    """往 llm_calls 表里写一行。

    返回 None —— 调用方不需要知道记账的结果，记账失败会直接抛异常上去。
    """
    # 造一行记录放进待写入区。
    db.add(
        LLMCall(
            purpose=purpose,
            provider=provider,
            model=model,
            prompt_text=prompt_text,
            response_text=response_text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            error=error,
        )
    )
    # 立刻提交，不等调用方。
    # ★ 为什么马上提交：如果等调用方一起提交，而调用方后面出错回滚了，
    #   这笔账也跟着没了——恰恰是出错时最需要留下记录。
    await db.commit()
