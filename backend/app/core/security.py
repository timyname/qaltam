from fastapi import Header, HTTPException, status

from backend.app.core.config import get_settings


def is_local_api_key_valid(x_api_key: str | None) -> bool:
    settings = get_settings()
    return bool(x_api_key and x_api_key == settings.quick_add_api_key)


def has_valid_local_api_key(x_api_key: str | None = Header(default=None, alias="X-API-KEY")) -> bool:
    return is_local_api_key_valid(x_api_key)


def validate_local_api_key(x_api_key: str = Header(alias="X-API-KEY")) -> str:
    if not is_local_api_key_valid(x_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return x_api_key
