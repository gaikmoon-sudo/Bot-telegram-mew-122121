from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_every_admin_api_route_has_a_permission_mapping():
    middleware = (ROOT / "app/authorization/middleware.py").read_text(encoding="utf-8")
    admin_api = (ROOT / "app/webapp/admin_api.py").read_text(encoding="utf-8")
    permissions = set(
        re.findall(r'^\s*"([^"]+)":\s*"[^"]+",', middleware, flags=re.MULTILINE)
    )
    routes = set(
        re.findall(
            r'\("(?:GET|POST|PATCH|PUT|DELETE)",\s*"[^"]+",\s*\w+,\s*"([^"]+)"\)',
            admin_api,
        )
    )
    assert routes - permissions == set()
