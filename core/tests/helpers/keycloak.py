# SPDX-FileCopyrightText: 2026 PSA_OVNCR
# SPDX-License-Identifier: Apache-2.0
"""Test helper: ``FakeKeycloakAdmin``, stub của ``dxos_core.registry.keycloak_admin.KeycloakAdmin`` (Plan 02
Task 12). Keycloak thật được kiểm ở e2e (Task 15)."""

from collections.abc import Sequence

from dxos_core.registry.keycloak_admin import IdpAdminUnavailable, _app_role_names


class FakeKeycloakAdmin:
    """``roles``: tập realm role đã tạo; ``down=True`` thì mọi lời gọi ném ``IdpAdminUnavailable``;
    ``default_composites``: composite của ``default-roles-dxos``; ``calls``: số lần ``ensure_app_roles``."""

    def __init__(self) -> None:
        self.roles: set[str] = set()
        self.down = False
        self.default_composites: list[str] = ["offline_access", "uma_authorization"]
        self.calls = 0

    async def ensure_app_roles(self, app_id: str, roles: Sequence[str]) -> list[str]:
        names = _app_role_names(app_id, roles)      # cùng luật tên với client thật
        if self.down:
            raise IdpAdminUnavailable("Keycloak admin POST /roles: ConnectError (giả lập)")
        self.calls += 1
        created = [n for n in names if n not in self.roles]
        self.roles.update(names)
        return created

    async def default_role_composites(self) -> list[str]:
        if self.down:
            raise IdpAdminUnavailable("Keycloak admin GET: ConnectError (giả lập)")
        return sorted(self.default_composites)
