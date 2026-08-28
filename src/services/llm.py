from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel

from src.core.config import Settings, get_settings

EFFECTIVE_LLM_TEMPERATURE = 0.0


class LLMConfigurationError(RuntimeError):
    """Raised when the real LLM cannot be configured safely."""


def get_llm(
    model: BaseChatModel | None = None,
    *,
    settings: Settings | None = None,
) -> BaseChatModel:
    """Return an injected model or lazily construct the configured OpenAI model.

    Supplying ``model`` is the test seam: settings, provider imports, credentials,
    and network-capable clients are all bypassed for a fake model.
    """
    if model is not None:
        return model

    resolved_settings = settings or get_settings()
    api_key = (resolved_settings.llm_api_key or "").strip()
    if not api_key:
        raise LLMConfigurationError(
            "LLM_API_KEY is not configured; set it before invoking the agent"
        )

    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=resolved_settings.llm_model,
        api_key=api_key,
        temperature=EFFECTIVE_LLM_TEMPERATURE,
        timeout=resolved_settings.llm_timeout_seconds,
        max_retries=resolved_settings.llm_max_retries,
    )


__all__ = ["EFFECTIVE_LLM_TEMPERATURE", "LLMConfigurationError", "get_llm"]
