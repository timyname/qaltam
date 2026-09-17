from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status

from backend.app.models.enums import WorkspaceRole


@dataclass(frozen=True)
class ActorContext:
    telegram_user_id: int
    telegram_chat_id: int
    workspace_role: WorkspaceRole


_ROLE_ALIASES = {
    "owner": WorkspaceRole.OWNER,
    "cfo": WorkspaceRole.CFO,
    "coo": WorkspaceRole.COO,
    "cashier": WorkspaceRole.CASHIER,
    "family": WorkspaceRole.FAMILY_MEMBER,
    "family_member": WorkspaceRole.FAMILY_MEMBER,
    "familymember": WorkspaceRole.FAMILY_MEMBER,
}


def _parse_workspace_role(raw_value: str | None) -> WorkspaceRole:
    if not raw_value:
        return WorkspaceRole.OWNER

    normalized = raw_value.strip().lower().replace("-", "_").replace(" ", "_")
    role = _ROLE_ALIASES.get(normalized)
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unsupported X-Qaltam-Role value.",
        )
    return role


def get_optional_actor_context(
    telegram_user_id: int | None = Header(default=None, alias="X-Telegram-User-Id"),
    telegram_chat_id: int | None = Header(default=None, alias="X-Telegram-Chat-Id"),
    workspace_role: str | None = Header(default=None, alias="X-Qaltam-Role"),
) -> ActorContext | None:
    if telegram_user_id is None and telegram_chat_id is None and workspace_role is None:
        return None

    if telegram_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Mini App requests must include X-Telegram-User-Id.",
        )

    return ActorContext(
        telegram_user_id=telegram_user_id,
        telegram_chat_id=telegram_chat_id or telegram_user_id,
        workspace_role=_parse_workspace_role(workspace_role),
    )


def require_actor_context(
    actor: ActorContext | None = Depends(get_optional_actor_context),
) -> ActorContext:
    if actor is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Mini App requests must include Telegram actor headers.",
        )
    return actor


def require_workspace_roles(*allowed_roles: WorkspaceRole) -> Callable[[ActorContext], ActorContext]:
    def dependency(actor: ActorContext = Depends(require_actor_context)) -> ActorContext:
        if actor.workspace_role not in allowed_roles:
            allowed = ", ".join(role.value for role in allowed_roles)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This route requires one of the following workspace roles: {allowed}.",
            )
        return actor

    return dependency


def ensure_actor_matches_identity(
    actor: ActorContext,
    *,
    telegram_user_id: int,
    telegram_chat_id: int | None = None,
) -> None:
    if actor.telegram_user_id != telegram_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Telegram actor does not match the requested telegram_user_id.",
        )

    if telegram_chat_id is not None and actor.telegram_chat_id != telegram_chat_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Telegram actor does not match the requested telegram_chat_id.",
        )
