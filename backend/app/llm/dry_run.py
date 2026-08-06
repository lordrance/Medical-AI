"""
================================================================================
文件作用：假的 AI 供应商 —— 返回固定的模拟内容，不联网不花钱
================================================================================

本地开发时用。什么时候会用上它：
  * 配置里写了 LLM_DRY_RUN=true
  * 或者 LLM_PROVIDER=deepseek 但没配 API key（自动降级到这里）

★ 第二种情况是刻意设计的：新人 clone 下项目、什么都不配也能把后台跑起来，
  点了 AI 总结按钮会看到一段"这是模拟内容"的提示，而不是卡在一个
  看不懂的报错上。

--------------------------------------------------------------------------------
本文件的代码块：
--------------------------------------------------------------------------------
  第 1 块  DryRunProvider   返回固定的模拟文本
================================================================================
"""

from __future__ import annotations

import time

from app.llm.base import LLMResponse


# ── 第 1 块：假供应商 ────────────────────────────────────────────────────
class DryRunProvider:
    """Returns canned, deterministic responses without calling any external API.

    Useful when developing without a real API key. Activated via env
    `LLM_DRY_RUN=true` or when DEEPSEEK_API_KEY is missing while
    LLM_PROVIDER=deepseek.
    """

    name: str = "dry_run"
    model: str = "dry-run-v1"

    async def generate(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> LLMResponse:
        """返回一段固定的模拟文本。

        "deterministic"（确定性）的意思是：同样的输入永远得到同样的输出。
        这一点对测试很重要——真 AI 每次生成的都不一样，没法写断言。
        """
        start = time.monotonic()
        # Tiny deterministic mock that quotes the user prompt.
        # 中文：文本里回显了提示词的长度，这样开发时一眼能看出
        # "提示词确实传进来了"，而不是空的。
        text = (
            "[DRY-RUN 模拟回复] 这是来自 dry-run provider 的模拟内容，"
            "未调用任何外部模型。\n\n"
            f"系统提示长度：{len(system)} 字\n"
            f"用户提示长度：{len(user)} 字\n"
            "—— 上线前请在 .env 配置 DEEPSEEK_API_KEY 并把 LLM_PROVIDER 设为 deepseek。"
        )
        latency = int((time.monotonic() - start) * 1000)
        return LLMResponse(
            text=text,
            model=self.model,
            provider=self.name,
            # 假的用量数字，直接拿字符数顶替。反正不真花钱，
            # 只是为了让返回结构和真供应商一致，上层代码不用分情况处理。
            prompt_tokens=len(system) + len(user),
            completion_tokens=len(text),
            latency_ms=latency,
        )

    async def health(self) -> bool:
        # 假供应商永远是"健康"的——它根本不依赖外部服务。
        return True
