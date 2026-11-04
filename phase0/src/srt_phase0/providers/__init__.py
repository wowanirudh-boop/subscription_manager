from .base import ExtractInput, Provider, RawExtraction, TriageInput, UsageStats
from .fake import FakeProvider


def get_provider(name: str, answers=None) -> Provider:
    if name == "fake":
        return FakeProvider()
    if name == "openrouter":
        from .openrouter import OpenRouterProvider

        return OpenRouterProvider()
    if name == "replay":
        from .replay import ReplayProvider

        return ReplayProvider(answers)
    raise ValueError(f"Unknown provider: {name!r} (expected 'fake', 'openrouter' or 'replay')")


__all__ = ["ExtractInput", "FakeProvider", "Provider", "RawExtraction", "TriageInput", "UsageStats", "get_provider"]
