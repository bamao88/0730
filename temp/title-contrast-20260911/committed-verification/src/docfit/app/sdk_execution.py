"""Shared metadata-only evidence derived from Claude Agent SDK results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from claude_agent_sdk.types import ResultMessage

from docfit.tools.runtime import JsonObject


@dataclass(frozen=True, slots=True)
class SDKResultMetrics:
    """Privacy-safe timing and usage facts shared by DocFit Agent modules."""

    num_turns: int = 0
    duration_ms: int = 0
    duration_api_ms: int = 0
    total_cost_usd: float | None = None
    usage: JsonObject | None = None

    @classmethod
    def from_result(cls, result: ResultMessage | None) -> SDKResultMetrics:
        if result is None:
            return cls()
        usage = _json_usage(result.usage)
        return cls(
            num_turns=result.num_turns,
            duration_ms=result.duration_ms,
            duration_api_ms=result.duration_api_ms,
            total_cost_usd=result.total_cost_usd,
            usage=usage,
        )

    def as_dict(self) -> JsonObject:
        return {
            "num_turns": self.num_turns,
            "duration_ms": self.duration_ms,
            "duration_api_ms": self.duration_api_ms,
            "total_cost_usd": self.total_cost_usd,
            "usage": dict(self.usage) if self.usage is not None else None,
        }


def _json_usage(value: Any) -> JsonObject | None:
    if not isinstance(value, dict):
        return None
    return {
        str(key): item
        for key, item in value.items()
        if isinstance(item, (str, int, float, bool, type(None)))
    }
