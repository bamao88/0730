"""Stateless template-domain mechanics and artifact publication."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from docfit.template.artifact import publish_template_artifact

__all__ = ["publish_template_artifact"]


def __getattr__(name: str) -> Any:
    if name == "publish_template_artifact":
        from docfit.template.artifact import publish_template_artifact

        return publish_template_artifact
    raise AttributeError(name)
