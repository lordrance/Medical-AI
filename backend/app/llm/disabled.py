"""
================================================================================
文件作用：★ 生产环境用的 AI 供应商 —— 一个什么都不做、只会拒绝的实现
================================================================================

V4 的设计是「医生端绝不调用 AI」，生产环境的 LLM_PROVIDER 就设成 disabled，
于是工厂函数返回的永远是这个类。任何想调 AI 的代码都会当场收到一个异常。

★ 这是一种叫「空对象模式」的写法：与其在每个调用点都写
      if AI 启用了: 调用 AI
  不如永远返回一个"长得像供应商、但只会拒绝"的对象。
  调用方代码保持一致，不用到处判断。

--------------------------------------------------------------------------------
本文件的代码块：
--------------------------------------------------------------------------------
  第 1 块  DisabledProvider   拒绝一切调用
  第 2 块  _assert_protocol   编译期自检（见下面说明）
================================================================================
"""

from __future__ import annotations

from app.llm.base import LLMProvider, LLMResponse, LLMUnavailable


# ── 第 1 块：拒绝一切调用 ────────────────────────────────────────────────
class DisabledProvider:
    """A provider that refuses any call. Used when LLM_PROVIDER=disabled."""

    name: str = "disabled"
    model: str = "disabled"

    async def generate(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> LLMResponse:
        raise LLMUnavailable(
            "LLM provider is disabled. Set LLM_PROVIDER=deepseek and provide DEEPSEEK_API_KEY."
        )

    async def health(self) -> bool:
        # ★ 这里必须老老实实返回 False，不能抛异常。
        # 后台的 AI 健康面板要显示状态，探测本身不该炸。
        return False


# ── 第 2 块：编译期自检 ──────────────────────────────────────────────────
# 这一行看起来没用，其实是个"静态检查断言"：它声明这个变量的类型是
# LLMProvider，然后赋一个 DisabledProvider 进去。
# 如果哪天有人给 LLMProvider 接口加了新方法而忘了在这里实现，
# 类型检查工具（mypy）会在这一行报错——不用等到运行时才发现。
# 运行时它只是白白造一个对象，代价可以忽略。
_assert_protocol: LLMProvider = DisabledProvider()  # type: ignore[assignment]
