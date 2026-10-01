"""Safe audit event construction for security-sensitive operations."""
from __future__ import annotations

from collections.abc import Mapping
from ipaddress import ip_address
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditLog, AuditOutcome

# Only these small, non-sensitive labels may be copied to audit details.
_SAFE_DETAIL_KEYS = frozenset({"permission", "route", "operation", "reason_code"})


def safe_ip(value: str | None) -> str | None:
    """Normalize a transport peer IP; never trust forwarded headers here."""
    if not value:
        return None
    try:
        return ip_address(value.strip()).compressed[:45]
    except ValueError:
        return None


def safe_details(details: Mapping[str, Any] | None) -> dict[str, str]:
    """Whitelist bounded metadata; values/payloads/secrets are never copied."""
    clean: dict[str, str] = {}
    if not isinstance(details, Mapping):
        return clean
    for key, value in details.items():
        if key in _SAFE_DETAIL_KEYS and isinstance(value, (str, int)):
            clean[key] = str(value)[:200]
    return clean


class AuditService:
    def __init__(self, session: AsyncSession):
        self.session = session

    def record(
        self,
        *,
        actor_user_id: int | None,
        action: str,
        resource_type: str,
        resource_id=None,
        resource_key: str | None = None,
        outcome: AuditOutcome,
        ip_address: str | None = None,
        user_agent: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> AuditLog:
        """Stage one non-sensitive audit row in the caller's transaction."""
        row = AuditLog(
            actor_user_id=actor_user_id,
            action=action[:100],
            resource_type=resource_type[:100],
            resource_id=resource_id,
            resource_key=(resource_key[:255] if resource_key else None),
            outcome=outcome,
            ip_address=safe_ip(ip_address),
            user_agent=(user_agent[:1024] if user_agent else None),
            details=safe_details(details),
        )
        self.session.add(row)
        return row
