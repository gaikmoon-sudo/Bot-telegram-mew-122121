"""One-time bootstrap of SUPER_ADMIN assignments for registered Telegram users.

Run after the runtime PostgreSQL schema is initialized and Alembic has upgraded:
    python scripts/bootstrap_admin_rbac.py --from-env
    python scripts/bootstrap_admin_rbac.py <telegram_user_id> [<telegram_user_id> ...]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, text

from app.audit.models import AuditOutcome
from app.audit.service import AuditService
from app.authorization.models import Role, UserRole
from config import settings
from infrastructure.database.session import session_factory


async def bootstrap(telegram_user_ids: list[int]) -> None:
    if session_factory is None:
        raise RuntimeError("DATABASE_URL is required to bootstrap an administrator")
    user_ids = sorted(set(telegram_user_ids))
    if not user_ids or any(user_id <= 0 for user_id in user_ids):
        raise ValueError("At least one positive Telegram user ID is required")

    async with session_factory() as session:
        async with session.begin():
            # Validate all subjects before making any assignment so the operation
            # remains atomic if one configured legacy administrator is unknown.
            for telegram_user_id in user_ids:
                registered_id = await session.scalar(
                    text("SELECT telegram_id FROM users WHERE telegram_id = :user_id"),
                    {"user_id": telegram_user_id},
                )
                if registered_id is None:
                    raise ValueError(
                        f"Telegram user {telegram_user_id} is not registered in the existing "
                        "Academy store; complete normal registration first."
                    )

            role = await session.scalar(select(Role).where(Role.name == "SUPER_ADMIN"))
            if role is None:
                raise RuntimeError("SUPER_ADMIN role is missing; apply the RBAC Alembic revision first")

            for telegram_user_id in user_ids:
                assignment = await session.get(UserRole, (telegram_user_id, role.id))
                if assignment is None:
                    session.add(UserRole(user_id=telegram_user_id, role_id=role.id))
                AuditService(session).record(
                    actor_user_id=None,
                    action="admin.bootstrap_super_admin",
                    resource_type="user_role",
                    resource_key=str(telegram_user_id),
                    outcome=AuditOutcome.SUCCESS,
                    details={"operation": "bootstrap_super_admin"},
                )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "telegram_user_ids",
        nargs="*",
        type=int,
        help="Registered Telegram user ID(s)",
    )
    parser.add_argument(
        "--from-env",
        action="store_true",
        help="Bootstrap every ID already listed in the existing ADMIN_IDS setting",
    )
    args = parser.parse_args()
    if args.from_env and args.telegram_user_ids:
        parser.error("provide Telegram IDs or --from-env, not both")
    user_ids = list(settings.admin_ids) if args.from_env else args.telegram_user_ids
    if not user_ids:
        parser.error("provide at least one Telegram ID or use --from-env")
    if any(user_id <= 0 for user_id in user_ids):
        parser.error("Telegram user IDs must be positive integers")
    asyncio.run(bootstrap(user_ids))
    print(f"SUPER_ADMIN role assigned to {len(set(user_ids))} user(s) and recorded in audit log.")


if __name__ == "__main__":
    main()
