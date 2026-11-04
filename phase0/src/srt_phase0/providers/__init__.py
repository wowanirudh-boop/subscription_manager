from .base import ExtractInput, Provider, RawExtraction, TriageInput, UsageStats
from .fake import FakeProvider


def get_provider(name: str) -> Provider:
    if name == "fake":
        return FakeProvider()
    if name == "openrouter":
        from .openrouter import OpenRouterProvider

        return OpenRouterProvider()
    raise ValueError(f"Unknown provider: {name!r} (expected 'fake' or 'openrouter')")


__all__ = ["ExtractInput", "FakeProvider", "Provider", "RawExtraction", "TriageInput", "UsageStats", "get_provider"]
