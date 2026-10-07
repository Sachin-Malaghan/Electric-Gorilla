from shunya.core.models.base import (
    ChatMessage,
    ModelProviderError,
    ModelResponse,
    ToolCallRequest,
    ToolResultBlock,
    ToolSpec,
    Usage,
)
from shunya.core.models.pricing import cost_usd
from shunya.core.models.router import ModelRouter, classify

__all__ = [
    "ChatMessage",
    "ModelProviderError",
    "ModelResponse",
    "ModelRouter",
    "ToolCallRequest",
    "ToolResultBlock",
    "ToolSpec",
    "Usage",
    "classify",
    "cost_usd",
]


def create_provider(settings, api_key: str | None = None):
    """Factory: the configured IModelProvider."""
    if settings.model_provider == "anthropic":
        from shunya.core.models.anthropic_provider import AnthropicProvider

        return AnthropicProvider(use_fallbacks=settings.model_fallbacks, api_key=api_key)
    if settings.model_provider == "scripted":
        from shunya.core.models.scripted_provider import ScriptedProvider
        from shunya.core.models.demo_scripts import demo_scripts

        return ScriptedProvider(demo_scripts(inject_compile_error=settings.demo_inject_compile_error), step_delay=settings.demo_step_delay)
    raise ValueError(f"unknown model provider '{settings.model_provider}' (expected anthropic | scripted)")
