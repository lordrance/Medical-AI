from __future__ import annotations

from app.core.config import get_settings
from app.llm.base import LLMProvider
from app.llm.deepseek import DeepseekProvider
from app.llm.disabled import DisabledProvider
from app.llm.dry_run import DryRunProvider


def get_provider() -> LLMProvider:
    """Build the LLM provider based on runtime configuration.

    Resolution order:
      * LLM_PROVIDER == "disabled"  -> DisabledProvider (always 503)
      * LLM_PROVIDER == "deepseek"  -> DeepseekProvider when DEEPSEEK_API_KEY set
                                       OR DryRunProvider when LLM_DRY_RUN=true
                                       OR DryRunProvider as fallback when key missing
                                       (with a warning, never silently break dev)

    中文：根据环境变量决定用哪个 AI 供应商。

    ★ 生产环境 LLM_PROVIDER=disabled，所以这个函数永远返回 DisabledProvider，
    任何调用都会直接抛 LLMUnavailable。这是 V4 的设计——医生端不许调 AI。
    你要用后台的 AI 总结功能，得先在 .env 里改成 deepseek 并配 API key。
    """
    s = get_settings()
    if s.LLM_PROVIDER == "disabled":
        return DisabledProvider()  # type: ignore[return-value]
    if s.LLM_PROVIDER == "deepseek":
        # ★ 没配 key 时降级成「假数据模式」而不是报错。
        # 这样新人 clone 下来不配任何东西也能把项目跑起来，
        # 不会卡在一个看不懂的报错上。
        if s.LLM_DRY_RUN or not s.DEEPSEEK_API_KEY:
            return DryRunProvider()  # type: ignore[return-value]
        return DeepseekProvider(  # type: ignore[return-value]
            api_key=s.DEEPSEEK_API_KEY,
            base_url=s.DEEPSEEK_BASE_URL,
            model=s.DEEPSEEK_MODEL,
            timeout_s=s.LLM_TIMEOUT_S,
        )
    # Defensive default
    # 中文：理论上走不到这里（配置项是枚举类型，只有两个值）。
    # 但万一将来加了新取值忘了在这里处理，默认「禁用」是最安全的
    # ——宁可不能用，也不要意外产生费用或泄露数据。
    return DisabledProvider()  # type: ignore[return-value]
