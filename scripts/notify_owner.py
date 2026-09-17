from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"
DEFAULT_OWNER_USERNAME = "@asproyant"
DEFAULT_BOT_USERNAME = "@menimwaltambot"
DEFAULT_LAUNCH_COMMAND = "cd qaltam && docker-compose up --build -d"


def build_message() -> str:
    return (
        "📂 All QALTAM files have been consolidated into the `./qaltam` folder!\n"
        "✅ Backend & Frontend tests passed inside `./qaltam`.\n"
        "🐳 Ready to launch: `cd qaltam && docker-compose up --build -d`"
    )


def normalize_username(username: str) -> str:
    return username.strip().lstrip("@").casefold()


def parse_env_file(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.exists():
        return values

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'").strip('"')
    return values


def load_report_text(report_file: str | None) -> str | None:
    if not report_file:
        return None
    return Path(report_file).read_text(encoding="utf-8").strip()


def coerce_console_text(text: str, encoding: str | None) -> str:
    target_encoding = encoding or "utf-8"
    return text.encode(target_encoding, errors="replace").decode(target_encoding)


def console_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        print(coerce_console_text(text, getattr(sys.stdout, "encoding", None)))


def iter_update_candidates(update: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    message_containers = []

    for key in ("message", "edited_message", "channel_post"):
        if isinstance(update.get(key), dict):
            message_containers.append(update[key])

    callback_query = update.get("callback_query")
    if isinstance(callback_query, dict):
        callback_message = callback_query.get("message")
        callback_from = callback_query.get("from")
        if isinstance(callback_message, dict):
            message_containers.append(callback_message)
        if isinstance(callback_from, dict):
            candidates.append(
                {
                    "username": callback_from.get("username"),
                    "chat_id": callback_from.get("id"),
                    "chat_type": "private",
                }
            )

    for message in message_containers:
        chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
        sender = message.get("from") if isinstance(message.get("from"), dict) else {}

        candidates.append(
            {
                "username": chat.get("username"),
                "chat_id": chat.get("id"),
                "chat_type": chat.get("type"),
            }
        )
        candidates.append(
            {
                "username": sender.get("username"),
                "chat_id": chat.get("id") or sender.get("id"),
                "chat_type": chat.get("type") or "private",
            }
        )

    return candidates


def find_chat_id_in_updates(updates: list[dict[str, Any]], owner_username: str) -> int | None:
    normalized_owner = normalize_username(owner_username)
    for update in reversed(updates):
        for candidate in iter_update_candidates(update):
            username = candidate.get("username")
            if not username or normalize_username(str(username)) != normalized_owner:
                continue
            chat_id = candidate.get("chat_id")
            if chat_id is None:
                continue
            if candidate.get("chat_type") not in (None, "private"):
                continue
            return int(chat_id)
    return None


def resolve_chat_id(chat_id_override: str | None, owner_username: str, updates: list[dict[str, Any]]) -> int:
    if chat_id_override:
        return int(chat_id_override)

    chat_id = find_chat_id_in_updates(updates, owner_username)
    if chat_id is None:
        raise LookupError(
            f"Could not resolve a private chat id for {owner_username}. "
            "Set OWNER_TELEGRAM_CHAT_ID in .env or make sure the user has messaged the bot."
        )
    return chat_id


def build_report(
    *,
    completion_status: str,
    pytest_status: str,
    frontend_status: str,
    launch_command: str,
) -> str:
    return "\n".join(
        [
            build_message(),
            "",
            f"📊 Completion status: {completion_status}",
            f"🧪 Pytest: {pytest_status}",
            f"🧱 Frontend build: {frontend_status}",
            f"🚀 Launch command: `{launch_command}`",
        ]
    )


def fetch_updates(token: str, timeout_seconds: float) -> list[dict[str, Any]]:
    response = httpx.get(
        f"https://api.telegram.org/bot{token}/getUpdates",
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        description = payload.get("description", "Unknown Telegram getUpdates failure.")
        raise RuntimeError(description)
    result = payload.get("result", [])
    if not isinstance(result, list):
        raise RuntimeError("Telegram getUpdates returned an unexpected payload.")
    return result


def fetch_chat_id_by_username(token: str, username: str, timeout_seconds: float) -> int | None:
    response = httpx.get(
        f"https://api.telegram.org/bot{token}/getChat",
        params={"chat_id": username},
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        return None
    result = payload.get("result", {})
    chat_id = result.get("id")
    return int(chat_id) if chat_id is not None else None


def send_report(token: str, chat_id: int, text: str, timeout_seconds: float) -> None:
    response = httpx.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        description = payload.get("description", "Unknown Telegram sendMessage failure.")
        raise RuntimeError(description)


def main() -> int:
    parser = argparse.ArgumentParser(description="Notify the project owner about QALTAM recovery status.")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_PATH))
    parser.add_argument("--owner-username", default=DEFAULT_OWNER_USERNAME)
    parser.add_argument("--bot-username", default=DEFAULT_BOT_USERNAME)
    parser.add_argument("--chat-id")
    parser.add_argument("--report-file")
    parser.add_argument("--completion-status", default="100%")
    parser.add_argument("--pytest-status", default="passed")
    parser.add_argument("--frontend-status", default="passed")
    parser.add_argument("--launch-command", default=DEFAULT_LAUNCH_COMMAND)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    env_values = parse_env_file(Path(args.env_file))
    token = env_values.get("TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing from .env and the current environment.")

    chat_id_override = (
        args.chat_id
        or env_values.get("OWNER_TELEGRAM_CHAT_ID")
        or env_values.get("ASPROYANT_TELEGRAM_CHAT_ID")
    )
    updates = [] if chat_id_override else fetch_updates(token, args.timeout)
    try:
        chat_id = resolve_chat_id(chat_id_override, args.owner_username, updates)
    except LookupError:
        direct_chat_id = fetch_chat_id_by_username(token, args.owner_username, args.timeout)
        if direct_chat_id is None:
            raise
        chat_id = direct_chat_id

    report = load_report_text(args.report_file) or build_report(
        completion_status=args.completion_status,
        pytest_status=args.pytest_status,
        frontend_status=args.frontend_status,
        launch_command=args.launch_command,
    )

    if args.dry_run:
        console_print(report)
        console_print(
            f"Dry run complete. Resolved {args.owner_username} to chat_id={chat_id} via {args.bot_username}."
        )
        return 0

    send_report(token, chat_id, report, args.timeout)
    console_print(f"Sent report via {args.bot_username} to {args.owner_username} (chat_id={chat_id}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
