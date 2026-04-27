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
    """
    s = get_settings()
    if s.LLM_PROVIDER == "disabled":
        return DisabledProvider()  # type: ignore[return-value]
    if s.LLM_PROVIDER == "deepseek":
        if s.LLM_DRY_RUN or not s.DEEPSEEK_API_KEY:
            return DryRunProvider()  # type: ignore[return-value]
        return DeepseekProvider(  # type: ignore[return-value]
            api_key=s.DEEPSEEK_API_KEY,
            base_url=s.DEEPSEEK_BASE_URL,
            model=s.DEEPSEEK_MODEL,
            timeout_s=s.LLM_TIMEOUT_S,
        )
    # Defensive default
    return DisabledProvider()  # type: ignore[return-value]
