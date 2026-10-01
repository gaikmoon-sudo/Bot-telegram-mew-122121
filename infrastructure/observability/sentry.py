"""Best-effort Sentry helpers used after Sentry is initialized by main."""
from __future__ import annotations
from collections.abc import Mapping
from typing import Any


def capture_exception(
    error: BaseException,
    *,
    tags: Mapping[str, str] | None = None,
    extras: Mapping[str, Any] | None = None,
) -> None:
    """Capture an exception without allowing observability to affect the bot."""
    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            for key, value in (tags or {}).items():
                scope.set_tag(str(key), str(value))
            for key, value in (extras or {}).items():
                scope.set_extra(str(key), value)
            sentry_sdk.capture_exception(error)
    except Exception:
        return
