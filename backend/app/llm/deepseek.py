"""
================================================================================
文件作用：真正调用 DeepSeek API 的实现
================================================================================

DeepSeek 用的是「OpenAI 兼容」的接口格式——也就是说它的调用方式和 OpenAI
一模一样，只是网址和密钥不同。所以这段代码稍加修改也能接别家。

★ 生产环境不会走到这个文件（LLM_PROVIDER=disabled）。只有你在服务器
  .env 里改成 deepseek 并配上 API key 之后，后台的 AI 总结功能才会用它。

--------------------------------------------------------------------------------
本文件的代码块：
--------------------------------------------------------------------------------
  第 1 块  DeepseekProvider.__init__()  记下密钥和参数
  第 2 块  generate()                   ★ 发一次请求，拿回生成的文本
  第 3 块  health()                     探测服务通不通
================================================================================
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.llm.base import LLMResponse, LLMUnavailable


class DeepseekProvider:
    """DeepSeek API provider (uses the OpenAI-compatible chat completions API)."""

    name: str = "deepseek"

    # ── 第 1 块：初始化 ────────────────────────────────────────────────
    def __init__(
        self,
        # 这个 * 表示后面的参数必须写名字传，防止把 base_url 和 model 传反。
        *,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
        timeout_s: float = 60.0,
    ) -> None:
        # 没密钥就当场报错，而不是等到真正调用时才失败。
        # 早失败比晚失败好排查。
        if not api_key:
            raise LLMUnavailable("DEEPSEEK_API_KEY is empty")
        self.api_key = api_key
        # rstrip("/") 去掉末尾的斜杠。不去的话下面拼出来会变成
        # "https://api.deepseek.com//chat/completions"，多一个斜杠可能 404。
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s

    # ── 第 2 块：生成文本 ★ ────────────────────────────────────────────
    async def generate(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> LLMResponse:
        """发一次请求，返回 AI 生成的文本。"""
        # monotonic 是"单调时钟"，只会往前走，不受系统时间调整影响。
        # 测耗时必须用它，用普通时钟的话用户改了系统时间会算出负数。
        start = time.monotonic()
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            # 温度 0.3 偏保守：同样的输入尽量给出稳定的输出。
            # 研究总结要的是可复现，不是创意。
            "temperature": temperature,
            # 不用流式返回。流式是为了让用户看到字一个个蹦出来，
            # 我们是后台批量生成，一次性拿全部结果更简单。
            "stream": False,
        }
        url = f"{self.base_url}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                resp = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
        except httpx.HTTPError as e:
            # 网络层面的失败（连不上、超时）。统一转成我们自己的异常类型，
            # 这样调用方只用处理一种异常，不用认识 httpx 的内部类型。
            raise LLMUnavailable(f"DeepSeek HTTP error: {e}") from e

        # 连上了但对方返回了错误码（密钥无效、余额不足、限流）。
        # 只取返回内容的前 500 字符，防止错误信息过长把日志刷爆。
        if resp.status_code != 200:
            raise LLMUnavailable(
                f"DeepSeek API returned {resp.status_code}: {resp.text[:500]}"
            )
        # 返回码是 200，但内容格式不一定对（对方改了接口、返回了空结果）。
        # 这一层 try 是防御性的：与其让 KeyError 冒到最上层变成 500，
        # 不如在这里转成"AI 不可用"，调用方能给出更合适的提示。
        try:
            data = resp.json()
            # 这一长串下标是 OpenAI 兼容格式的固定结构：
            # {"choices": [{"message": {"content": "生成的文本"}}], "usage": {...}}
            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage") or {}   # 用量信息，可能没有
        except Exception as e:
            raise LLMUnavailable(f"DeepSeek bad response shape: {e}") from e

        latency = int((time.monotonic() - start) * 1000)
        return LLMResponse(
            text=text,
            model=self.model,
            provider=self.name,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            latency_ms=latency,
        )

    # ── 第 3 块：健康探测 ──────────────────────────────────────────────
    async def health(self) -> bool:
        """探测服务通不通。后台的 AI 健康面板会显示这个结果。"""
        # Cheap probe: HEAD the base url; failure is acceptable.
        # 中文：只是访问一下首页看有没有响应，不真的生成文本——
        # 真生成一次要花钱也要花时间，健康检查不值当。
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{self.base_url}/")
                # 小于 500 就算通：404 也说明服务器是活的，只是这个路径没内容。
                # 只有 5xx（服务器自己坏了）和连不上才算不通。
                return r.status_code < 500
        except httpx.HTTPError:
            return False
