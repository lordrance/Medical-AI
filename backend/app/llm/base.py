"""
================================================================================
文件作用：AI 供应商的「统一接口」定义 —— 规定一个供应商该长什么样
================================================================================

这里不实现任何具体功能，只规定"接口长什么样"。有了这层约定，上层代码
不用关心背后是 DeepSeek 还是别家，换供应商只要新写一个类、改一行配置。

★ 再强调一次：V4 的医生端完全不调用 AI。整个 llm/ 目录只服务于后台的
  「生成研究总结」功能，你不点那个按钮它一行都不会执行。

同目录下有三个实现：
  disabled.py   什么都不做，直接抛异常  ← ★ 生产环境用的就是这个
  deepseek.py   真的调 DeepSeek 的 API
  dry_run.py    返回假数据，本地开发用，不花钱不联网

--------------------------------------------------------------------------------
本文件的代码块：
--------------------------------------------------------------------------------
  第 1 块  LLMResponse     一次调用的结果长什么样
  第 2 块  LLMUnavailable  AI 不可用时抛的异常
  第 3 块  LLMProvider     ★ 供应商必须实现的两个方法
================================================================================
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel


# ── 第 1 块：调用结果 ────────────────────────────────────────────────────
class LLMResponse(BaseModel):
    """一次 AI 调用的结果。这些字段会被 llm_audit 原样记进账本。"""

    text: str                              # AI 生成的文本
    model: str                             # 用的哪个模型
    provider: str                          # 哪家供应商
    prompt_tokens: int | None = None       # 输入消耗的 token（算钱用）
    completion_tokens: int | None = None   # 输出消耗的 token
    latency_ms: int                        # 耗时


# ── 第 2 块：AI 不可用异常 ───────────────────────────────────────────────
class LLMUnavailable(Exception):
    """Raised when an LLM call cannot be made (provider disabled or upstream error).

    中文：AI 不可用时抛这个。调用方 catch 它并返回 503，
    而不是让它变成 500 —— 「AI 服务暂时不可用」和「代码有 bug」是两回事。
    """


# ── 第 3 块：供应商接口 ★ ───────────────────────────────────────────────
class LLMProvider(Protocol):
    """供应商必须实现的方法。

    Protocol 是 Python 的「鸭子类型」写法：不需要显式继承，
    只要一个类有这些方法和属性，就能当 LLMProvider 用。
    """

    name: str
    model: str

    async def generate(
        self,
        *,
        system: str,       # 系统提示词（设定 AI 的角色和规则）
        user: str,         # 用户提示词（具体要它干什么）
        max_tokens: int = 1024,
        # 温度 0.3：偏保守、结果稳定。研究总结要的是可复现，不是创意。
        temperature: float = 0.3,
    ) -> LLMResponse:
        """Generate a completion. Raise LLMUnavailable on failure."""
        ...

    async def health(self) -> bool:
        """Lightweight health check; should not raise on disabled provider.

        中文：探测 AI 服务通不通。★ 即使供应商是 disabled 也不能抛异常，
        应该老老实实返回 False —— 后台的健康面板要显示这个状态。
        """
        ...
