from __future__ import annotations

from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from backend.app.core.config import get_settings

WebAppTab = Literal["map", "cashier", "quick", "sandbox", "settings"]
WebAppFocus = Literal["clarify", "statement"]


def _normalize_webapp_base_url(url: str) -> str:
    parts = urlsplit(url)
    normalized_path = parts.path if parts.path.endswith("/") else f"{parts.path}/"
    return urlunsplit(parts._replace(path=normalized_path))


def build_webapp_url(
    *,
    tab: WebAppTab | None = None,
    focus: WebAppFocus | None = None,
    statement_id: int | None = None,
    telegram_user_id: int | None = None,
    telegram_chat_id: int | None = None,
) -> str:
    base_url = _normalize_webapp_base_url(get_settings().telegram_webapp_url)
    if tab is None and focus is None and statement_id is None and telegram_user_id is None and telegram_chat_id is None:
        return base_url

    parts = urlsplit(base_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if tab is not None:
        query["tab"] = tab
    if focus is not None:
        query["focus"] = focus
    if statement_id is not None:
        query["statement_id"] = str(statement_id)
    if telegram_user_id is not None:
        query["telegram_user_id"] = str(telegram_user_id)
    if telegram_chat_id is not None:
        query["telegram_chat_id"] = str(telegram_chat_id)
    return urlunsplit(parts._replace(query=urlencode(query)))
