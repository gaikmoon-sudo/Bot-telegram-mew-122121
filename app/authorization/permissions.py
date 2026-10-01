"""Permission catalog and built-in role grants for the Academy admin system.

Authorization decisions are always made from permission keys (resource.action),
not from role-name checks in handlers. The wildcard permission is deliberately
reserved for SUPER_ADMIN and also covers permissions added in future releases.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PermissionSpec:
    resource: str
    action: str
    description: str

    @property
    def key(self) -> str:
        return f"{self.resource}.{self.action}"


# Keep this catalog additive. A newly introduced permission is denied by
# default unless granted by a role or by an explicit user-level override.
_PERMISSION_ROWS = (
    ("*", "*", "All current and future permissions"),
    ("admin", "dashboard.view", "View the administrative landing page"),
    ("analytics", "view", "View administrative analytics"),
    ("users", "view", "View user records"),
    ("users", "manage", "Manage user accounts"),
    ("courses", "view", "View courses"),
    ("courses", "create", "Create courses"),
    ("courses", "edit", "Edit courses"),
    ("courses", "delete", "Delete courses"),
    ("modules", "view", "View modules"),
    ("modules", "create", "Create modules"),
    ("modules", "edit", "Edit modules"),
    ("modules", "delete", "Delete modules"),
    ("lessons", "view", "View lessons"),
    ("lessons", "create", "Create lessons"),
    ("lessons", "edit", "Edit lessons"),
    ("lessons", "delete", "Delete lessons"),
    ("text", "edit", "Edit lesson and course text"),
    ("content", "order", "Change content ordering"),
    ("files", "view", "View content files"),
    ("files", "upload", "Upload content files"),
    ("files", "delete", "Delete content files"),
    ("videos", "add_link", "Add or update video links"),
    ("videos", "manage", "Manage all video links"),
    ("images", "manage", "Manage course images"),
    ("ai", "manage", "Manage AI features and configuration"),
    ("payments", "view", "View payment records"),
    ("payments", "manage", "Manage payments and refunds"),
    ("certificates", "manage", "Manage certificates"),
    ("notifications", "manage", "Manage and send notifications"),
    ("bot", "settings", "Manage bot settings"),
    ("admins", "manage", "Manage administrator assignments"),
    ("permissions", "manage", "Manage roles and permissions"),
    ("security", "logs.view", "View security and audit logs"),
    ("security", "settings", "Manage security settings"),
    ("settings", "manage", "Manage system settings"),
)

PERMISSION_CATALOG: dict[str, PermissionSpec] = {
    f"{resource}.{action}": PermissionSpec(resource, action, description)
    for resource, action, description in _PERMISSION_ROWS
}

SUPER_ADMIN = "SUPER_ADMIN"
CONTENT_MANAGER = "CONTENT_MANAGER"
CONTENT_EDITOR = "CONTENT_EDITOR"
BUILTIN_ROLES = (SUPER_ADMIN, CONTENT_MANAGER, CONTENT_EDITOR)

# A content manager may create, edit, reorder and remove educational assets,
# but receives no user, payment, AI, bot, settings, administrator or security
# permissions. The editor gets a smaller set focused on lesson updates only.
ROLE_GRANTS: dict[str, frozenset[str]] = {
    SUPER_ADMIN: frozenset({"*.*"}),
    CONTENT_MANAGER: frozenset(
        {
            "courses.view", "courses.create", "courses.edit", "courses.delete",
            "modules.view", "modules.create", "modules.edit", "modules.delete",
            "lessons.view", "lessons.create", "lessons.edit", "lessons.delete",
            "text.edit", "content.order", "files.view", "files.upload",
            "files.delete", "videos.manage", "images.manage",
        }
    ),
    CONTENT_EDITOR: frozenset(
        {
            "lessons.view", "lessons.edit", "text.edit", "videos.add_link",
            "files.view", "files.upload",
        }
    ),
}


def permission_matches(granted_key: str, requested_key: str) -> bool:
    """Return whether a grant (including resource/action wildcards) matches."""
    try:
        granted_resource, granted_action = granted_key.split(".", 1)
        requested_resource, requested_action = requested_key.split(".", 1)
    except ValueError:
        return False
    return (granted_resource in {"*", requested_resource}) and (
        granted_action in {"*", requested_action}
    )


def evaluate_permissions(
    requested_key: str,
    *,
    role_grants: set[str] | frozenset[str] = frozenset(),
    user_overrides: dict[str, bool] | None = None,
) -> bool:
    """Evaluate grants with explicit per-user decisions taking precedence.

    An explicit user denial wins over role or wildcard grants. An explicit user
    grant can provide a narrowly scoped capability absent from assigned roles.
    All other requests are denied by default.
    """
    overrides = user_overrides or {}
    matching = [
        (key, grant)
        for key, grant in overrides.items()
        if permission_matches(key, requested_key)
    ]
    # Any explicit denial wins, including a resource-wide or global denial.
    if any(grant is False for _key, grant in matching):
        return False
    if any(grant is True for _key, grant in matching):
        return True
    return any(permission_matches(grant, requested_key) for grant in role_grants)
