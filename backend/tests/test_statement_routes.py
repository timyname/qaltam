from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path

from fastapi.testclient import TestClient
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.api.v1.routes import statements as statement_routes
from backend.app.core.config import get_settings
from backend.app.db.base import Base
from backend.app.db.database import get_session
from backend.app.localization import text
from backend.app.main import create_app
from backend.app.models.profile import ImportedStatement
from backend.app.models.transaction import Transaction


def actor_headers(
    telegram_user_id: int = 9001,
    telegram_chat_id: int = 9001,
    role: str = "owner",
) -> dict[str, str]:
    return {
        "X-Telegram-User-Id": str(telegram_user_id),
        "X-Telegram-Chat-Id": str(telegram_chat_id),
        "X-Qaltam-Role": role,
    }


@pytest_asyncio.fixture
async def statement_client() -> AsyncGenerator[tuple[TestClient, async_sessionmaker[AsyncSession]], None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    settings = get_settings()
    original_deepseek_api_key = settings.deepseek_api_key
    settings.deepseek_api_key = ""

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = override_get_session

    with TestClient(app) as client:
        yield client, session_factory

    app.dependency_overrides.clear()
    settings.deepseek_api_key = original_deepseek_api_key
    await engine.dispose()


@pytest.mark.asyncio
async def test_statement_routes_import_and_clarify(statement_client) -> None:
    client, session_factory = statement_client
    language = "ru"

    import_response = client.post(
        "/api/v1/statements/import-text",
        headers=actor_headers(),
        json={
            "telegram_user_id": 9001,
            "telegram_chat_id": 9001,
            "raw_text": "2026-08-10 Client LLP +150000\n2026-08-11 Arman T. -45000",
            "language": language,
        },
    )
    assert import_response.status_code == 200
    import_payload = import_response.json()
    assert import_payload["parsed_count"] == 2
    assert import_payload["unclear_count"] == 2
    assert import_payload["summary_message"] == text(
        "statement_processing_summary",
        language,
        parsed_count=2,
        auto_count=0,
        unclear_count=2,
    )
    assert import_payload["prompt_message"].startswith(
        text("statement_prompt_intro", language, auto_count=0, ordinal=1, total=2)
    )
    assert import_payload["pending"] is not None
    assert import_payload["pending"]["current_index"] == 0
    assert import_payload["pending"]["total_count"] == 2
    assert import_payload["pending"]["resolved_count"] == 0
    assert import_payload["pending"]["remaining_count"] == 2
    assert import_payload["pending"]["current_item"]["counterparty"] == "Client LLP"
    assert import_payload["pending"]["current_item"]["matched_rules"] == []
    assert import_payload["pending"]["prompt_message"].startswith(
        text("statement_prompt_intro", language, auto_count=0, ordinal=1, total=2)
    )
    assert import_payload["latest_status"]["parse_status"] == "clarification_required"
    assert import_payload["latest_status"]["remaining_clarifications"] == 2
    assert import_payload["history"][0]["remaining_clarifications"] == 2

    pending_response = client.get(
        "/api/v1/statements/pending",
        headers=actor_headers(),
        params={"telegram_user_id": 9001, "language": language},
    )
    assert pending_response.status_code == 200
    pending_payload = pending_response.json()
    assert pending_payload["current_index"] == 0
    assert pending_payload["total_count"] == 2
    assert pending_payload["resolved_count"] == 0
    assert pending_payload["remaining_count"] == 2
    assert len(pending_payload["items"]) == 2
    assert pending_payload["items"][0]["counterparty"] == "Client LLP"
    assert pending_payload["items"][0]["matched_rules"] == []
    assert pending_payload["current_item"]["counterparty"] == "Client LLP"
    assert pending_payload["current_item"]["matched_rules"] == []
    assert pending_payload["prompt_message"].startswith(
        text("statement_prompt_intro", language, auto_count=0, ordinal=1, total=2)
    )

    status_response = client.get(
        "/api/v1/statements/status",
        headers=actor_headers(),
        params={"telegram_user_id": 9001, "language": language},
    )
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["pending"] is not None
    assert status_payload["pending"]["total_count"] == 2
    assert status_payload["pending"]["resolved_count"] == 0
    assert status_payload["pending"]["remaining_count"] == 2
    assert status_payload["pending"]["current_item"]["counterparty"] == "Client LLP"
    assert status_payload["pending"]["current_item"]["matched_rules"] == []
    assert status_payload["pending"]["prompt_message"].startswith(
        text("statement_prompt_intro", language, auto_count=0, ordinal=1, total=2)
    )
    assert status_payload["latest_status"]["parse_status"] == "clarification_required"
    assert status_payload["latest_status"]["remaining_clarifications"] == 2
    assert status_payload["latest_status"]["unclear_count"] == 2

    first_clarification = client.post(
        "/api/v1/statements/clarify",
        headers=actor_headers(),
        json={
            "telegram_user_id": 9001,
            "telegram_chat_id": 9001,
            "account_type": "business",
            "life_sector": "sales_income",
            "language": language,
        },
    )
    assert first_clarification.status_code == 200
    first_payload = first_clarification.json()
    assert first_payload["message"].startswith(text("statement_next_clarification", language, ordinal=2, total=2))
    assert first_payload["pending"] is not None
    assert first_payload["pending"]["current_index"] == 1
    assert first_payload["pending"]["total_count"] == 2
    assert first_payload["pending"]["resolved_count"] == 1
    assert first_payload["pending"]["remaining_count"] == 1
    assert first_payload["pending"]["current_item"]["counterparty"] == "Arman T."
    assert first_payload["pending"]["prompt_message"].startswith(
        text("statement_prompt_intro", language, auto_count=0, ordinal=2, total=2)
    )
    assert first_payload["latest_status"]["parse_status"] == "clarification_required"
    assert first_payload["latest_status"]["remaining_clarifications"] == 1
    assert first_payload["history"][0]["remaining_clarifications"] == 1

    second_clarification = client.post(
        "/api/v1/statements/clarify",
        headers=actor_headers(),
        json={
            "telegram_user_id": 9001,
            "telegram_chat_id": 9001,
            "account_type": "business",
            "life_sector": "inventory_parts",
            "language": language,
        },
    )
    assert second_clarification.status_code == 200
    second_payload = second_clarification.json()
    assert second_payload["message"] == text("statement_completion_saved", language)
    assert second_payload["pending"] is None
    assert second_payload["latest_status"]["parse_status"] == "completed"
    assert second_payload["latest_status"]["remaining_clarifications"] == 0
    assert second_payload["history"][0]["remaining_clarifications"] == 0

    no_pending_response = client.get(
        "/api/v1/statements/pending",
        headers=actor_headers(),
        params={"telegram_user_id": 9001},
    )
    assert no_pending_response.status_code == 200
    assert no_pending_response.json() is None

    final_status_response = client.get(
        "/api/v1/statements/status",
        headers=actor_headers(),
        params={"telegram_user_id": 9001, "language": language},
    )
    assert final_status_response.status_code == 200
    final_status_payload = final_status_response.json()
    assert final_status_payload["pending"] is None
    assert final_status_payload["latest_status"]["parse_status"] == "completed"
    assert final_status_payload["latest_status"]["remaining_clarifications"] == 0
    assert final_status_payload["latest_status"]["unclear_count"] == 0

    async with session_factory() as session:
        categories = list((await session.execute(select(Transaction.category).order_by(Transaction.id.asc()))).scalars())
        assert categories == ["sales_income", "inventory_parts"]


@pytest.mark.asyncio
async def test_statement_routes_accept_spoken_ordinal_answer_text_for_clarification(statement_client) -> None:
    client, session_factory = statement_client
    language = "kk"

    import_response = client.post(
        "/api/v1/statements/import-text",
        headers=actor_headers(),
        json={
            "telegram_user_id": 9001,
            "telegram_chat_id": 9001,
            "raw_text": "2026-08-10 Client LLP +150000\n2026-08-11 Arman T. -45000",
            "language": language,
        },
    )
    assert import_response.status_code == 200

    clarify_response = client.post(
        "/api/v1/statements/clarify",
        headers=actor_headers(),
        json={
            "telegram_user_id": 9001,
            "telegram_chat_id": 9001,
            "answer_text": "бірінші нұсқа",
            "language": language,
        },
    )

    assert clarify_response.status_code == 200
    payload = clarify_response.json()
    assert payload["message"].startswith(text("statement_next_clarification", language, ordinal=2, total=2))
    assert payload["pending"] is not None
    assert payload["pending"]["current_index"] == 1
    assert payload["pending"]["remaining_count"] == 1
    assert payload["latest_status"]["parse_status"] == "clarification_required"
    assert payload["latest_status"]["remaining_clarifications"] == 1

    async with session_factory() as session:
        categories = list((await session.execute(select(Transaction.category).order_by(Transaction.id.asc()))).scalars())
        assert categories == ["sales_income"]


@pytest.mark.asyncio
async def test_statement_routes_import_single_statement_row(statement_client) -> None:
    client, session_factory = statement_client

    import_response = client.post(
        "/api/v1/statements/import-text",
        headers=actor_headers(),
        json={
            "telegram_user_id": 9001,
            "telegram_chat_id": 9001,
            "raw_text": "2026-08-10 Client LLP +150000",
        },
    )
    assert import_response.status_code == 200
    import_payload = import_response.json()
    assert import_payload["parsed_count"] == 1
    assert import_payload["auto_count"] == 0
    assert import_payload["unclear_count"] == 1
    assert "Processing bank statement (1 items)" in import_payload["summary_message"]
    assert "Clarification 1 of 1" in import_payload["prompt_message"]
    assert import_payload["pending"] is not None
    assert import_payload["pending"]["current_index"] == 0
    assert import_payload["pending"]["total_count"] == 1
    assert import_payload["pending"]["resolved_count"] == 0
    assert import_payload["pending"]["remaining_count"] == 1
    assert import_payload["pending"]["current_item"]["counterparty"] == "Client LLP"
    assert import_payload["latest_status"]["parse_status"] == "clarification_required"
    assert import_payload["latest_status"]["remaining_clarifications"] == 1
    assert import_payload["history"][0]["remaining_clarifications"] == 1

    status_response = client.get(
        "/api/v1/statements/status",
        headers=actor_headers(),
        params={"telegram_user_id": 9001},
    )
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["pending"] is not None
    assert status_payload["pending"]["total_count"] == 1
    assert status_payload["pending"]["resolved_count"] == 0
    assert status_payload["pending"]["remaining_count"] == 1
    assert status_payload["pending"]["current_item"]["counterparty"] == "Client LLP"
    assert status_payload["latest_status"]["parse_status"] == "clarification_required"

    async with session_factory() as session:
        categories = list((await session.execute(select(Transaction.category).order_by(Transaction.id.asc()))).scalars())
        assert categories == []


@pytest.mark.asyncio
async def test_statement_routes_import_file_and_open_clarification(statement_client, monkeypatch, tmp_path) -> None:
    client, _ = statement_client
    settings = get_settings()
    monkeypatch.setattr(settings, "local_storage_path", tmp_path, raising=False)

    upload_response = client.post(
        "/api/v1/statements/import-file",
        headers=actor_headers(),
        data={
            "telegram_user_id": "9001",
            "telegram_chat_id": "9001",
        },
        files={
            "file": (
                "kaspi_statement.csv",
                "\n".join(
                    [
                        "date,amount,counterparty,description",
                        "2026-08-10,150000,Client LLP,Kaspi incoming client payment",
                        "2026-08-11,-45000,Arman T.,Kaspi transfer to supplier",
                    ]
                ).encode("utf-8"),
                "text/csv",
            )
        },
    )

    assert upload_response.status_code == 200
    payload = upload_response.json()
    assert payload["parsed_count"] == 2
    assert payload["unclear_count"] == 2
    assert "Processing bank statement (2 items)" in payload["summary_message"]
    assert "Clarification 1 of 2" in payload["prompt_message"]
    assert "Statement note: Kaspi incoming client payment" in payload["prompt_message"]
    assert payload["pending"] is not None
    assert payload["pending"]["current_index"] == 0
    assert payload["pending"]["total_count"] == 2
    assert payload["pending"]["resolved_count"] == 0
    assert payload["pending"]["remaining_count"] == 2
    assert payload["pending"]["current_item"]["counterparty"] == "Client LLP"
    assert payload["latest_status"]["parse_status"] == "clarification_required"
    assert payload["latest_status"]["remaining_clarifications"] == 2
    assert payload["history"][0]["remaining_clarifications"] == 2

    pending_response = client.get(
        "/api/v1/statements/pending",
        headers=actor_headers(),
        params={"telegram_user_id": 9001},
    )
    assert pending_response.status_code == 200
    pending_payload = pending_response.json()
    assert pending_payload["items"][0]["counterparty"] == "Client LLP"
    assert pending_payload["current_item"]["counterparty"] == "Client LLP"
    upload_dir = Path(tmp_path) / "imports" / "webapp" / "statements"
    assert upload_dir.exists()
    stored_files = list(upload_dir.iterdir())
    assert len(stored_files) == 1
    assert stored_files[0].suffix == ".csv"


@pytest.mark.asyncio
async def test_statement_routes_persist_uploaded_file_path_in_statement_history(statement_client, monkeypatch, tmp_path) -> None:
    client, session_factory = statement_client
    settings = get_settings()
    monkeypatch.setattr(settings, "local_storage_path", tmp_path, raising=False)

    upload_response = client.post(
        "/api/v1/statements/import-file",
        headers=actor_headers(),
        data={
            "telegram_user_id": "9001",
            "telegram_chat_id": "9001",
        },
        files={
            "file": (
                "halyk_statement.csv",
                "\n".join(
                    [
                        "date,amount,counterparty,description",
                        "2026-08-10,150000,Client LLP,Kaspi incoming client payment",
                    ]
                ).encode("utf-8"),
                "text/csv",
            )
        },
    )

    assert upload_response.status_code == 200

    async with session_factory() as session:
        statement = (
            await session.execute(
                select(ImportedStatement).where(ImportedStatement.original_filename == "halyk_statement.csv")
            )
        ).scalars().one()

    stored_path = Path(statement.file_path)
    assert stored_path.exists()
    assert stored_path.parent == tmp_path / "imports" / "webapp" / "statements"
    assert stored_path.suffix == ".csv"


@pytest.mark.asyncio
async def test_statement_routes_import_semicolon_cp1251_file(statement_client) -> None:
    client, _ = statement_client

    csv_payload = "\n".join(
        [
            "\u0414\u0430\u0442\u0430;\u0421\u0443\u043c\u043c\u0430;\u041a\u043e\u043d\u0442\u0440\u0430\u0433\u0435\u043d\u0442;\u041d\u0430\u0437\u043d\u0430\u0447\u0435\u043d\u0438\u0435 \u043f\u043b\u0430\u0442\u0435\u0436\u0430",
            "10.08.2026;150000,00;\u041a\u043b\u0438\u0435\u043d\u0442 \u0422\u041e\u041e;\u041f\u043e\u043f\u043e\u043b\u043d\u0435\u043d\u0438\u0435 \u043e\u0442 \u043a\u043b\u0438\u0435\u043d\u0442\u0430",
            "11.08.2026;-45000,50;\u0410\u0440\u043c\u0430\u043d \u0422.;\u041f\u0435\u0440\u0435\u0432\u043e\u0434 \u043f\u043e\u0441\u0442\u0430\u0432\u0449\u0438\u043a\u0443",
        ]
    ).encode("cp1251")

    upload_response = client.post(
        "/api/v1/statements/import-file",
        headers=actor_headers(),
        data={
            "telegram_user_id": "9001",
            "telegram_chat_id": "9001",
        },
        files={
            "file": (
                "halyk_statement.csv",
                csv_payload,
                "text/csv",
            )
        },
    )

    assert upload_response.status_code == 200
    payload = upload_response.json()
    assert payload["parsed_count"] == 2
    assert payload["unclear_count"] == 2
    assert payload["pending"] is not None
    assert payload["pending"]["current_item"]["counterparty"] == "\u041a\u043b\u0438\u0435\u043d\u0442 \u0422\u041e\u041e"
    assert payload["history"][0]["original_filename"] == "halyk_statement.csv"


@pytest.mark.asyncio
async def test_statement_history_route_returns_recent_imports_with_live_remaining_counts(statement_client) -> None:
    client, _ = statement_client

    first_import = client.post(
        "/api/v1/statements/import-text",
        headers=actor_headers(),
        json={
            "telegram_user_id": 9001,
            "telegram_chat_id": 9001,
            "raw_text": "2026-08-08 Client LLP +150000\n2026-08-09 Arman T. -45000",
        },
    )
    assert first_import.status_code == 200
    first_import_payload = first_import.json()

    first_clarification = client.post(
        "/api/v1/statements/clarify",
        headers=actor_headers(),
        json={
            "telegram_user_id": 9001,
            "telegram_chat_id": 9001,
            "account_type": "business",
            "life_sector": "sales_income",
        },
    )
    assert first_clarification.status_code == 200

    second_clarification = client.post(
        "/api/v1/statements/clarify",
        headers=actor_headers(),
        json={
            "telegram_user_id": 9001,
            "telegram_chat_id": 9001,
            "account_type": "business",
            "life_sector": "inventory_parts",
        },
    )
    assert second_clarification.status_code == 200

    second_import = client.post(
        "/api/v1/statements/import-text",
        headers=actor_headers(),
        json={
            "telegram_user_id": 9001,
            "telegram_chat_id": 9001,
            "raw_text": "2026-08-10 Kaspi Incoming +99000\n2026-08-11 Magnum -18250",
        },
    )
    assert second_import.status_code == 200
    second_import_payload = second_import.json()

    history_response = client.get(
        "/api/v1/statements/history",
        headers=actor_headers(),
        params={"telegram_user_id": 9001, "limit": 5},
    )

    assert history_response.status_code == 200
    payload = history_response.json()
    assert len(payload["items"]) == 2
    assert payload["items"][0]["original_filename"] == "telegram_text_statement.txt"
    assert payload["items"][0]["parse_status"] == "clarification_required"
    assert payload["items"][0]["remaining_clarifications"] == 2
    assert payload["items"][0]["unclear_count"] == 2
    assert payload["items"][0]["parsed_count"] == second_import_payload["parsed_count"]
    assert payload["items"][0]["auto_count"] == second_import_payload["auto_count"]
    assert payload["items"][1]["remaining_clarifications"] == 0
    assert payload["items"][1]["parse_status"] == "completed"
    assert payload["items"][1]["unclear_count"] == 0
    assert payload["items"][1]["parsed_count"] == first_import_payload["parsed_count"]
    assert payload["items"][1]["auto_count"] == first_import_payload["auto_count"]


@pytest.mark.asyncio
async def test_statement_detail_route_returns_active_preview_and_pending_context(statement_client) -> None:
    client, _ = statement_client

    raw_text = "\n".join(
        [
            "2026-08-10 Client LLP +150000",
            "2026-08-11 Arman T. -45000",
            "2026-08-12 Kaspi Incoming +99000",
            "2026-08-13 Magnum -18250",
            "2026-08-14 Logistics Hub -55000",
            "2026-08-15 Marketing Team -20000",
            "2026-08-16 Family Transfer -17000",
            "2026-08-17 Tax Office -33000",
            "2026-08-18 SaaS Renewals -9900",
            "2026-08-19 Owner Draw -25000",
            "2026-08-20 Supplier One -75000",
            "2026-08-21 Supplier Two -81000",
            "2026-08-22 Supplier Three -42000",
        ]
    )
    import_response = client.post(
        "/api/v1/statements/import-text",
        headers=actor_headers(),
        json={
            "telegram_user_id": 9001,
            "telegram_chat_id": 9001,
            "raw_text": raw_text,
            "language": "en",
        },
    )
    assert import_response.status_code == 200
    imported_statement_id = import_response.json()["imported_statement_id"]

    detail_response = client.get(
        f"/api/v1/statements/detail/{imported_statement_id}",
        headers=actor_headers(),
        params={"telegram_user_id": 9001, "language": "en"},
    )

    assert detail_response.status_code == 200
    payload = detail_response.json()
    assert payload["imported_statement_id"] == imported_statement_id
    assert payload["storage_kind"] == "virtual_text"
    assert payload["file_available"] is False
    assert payload["is_active"] is True
    assert payload["remaining_clarifications"] == 13
    assert payload["pending"] is not None
    assert payload["pending"]["statement_id"] == imported_statement_id
    assert payload["raw_line_count"] == 13
    assert payload["raw_preview_truncated"] is True
    assert "2026-08-10 Client LLP +150000" in payload["raw_preview"]
    assert "2026-08-21 Supplier Two -81000" in payload["raw_preview"]
    assert "2026-08-22 Supplier Three -42000" not in payload["raw_preview"]


@pytest.mark.asyncio
async def test_statement_detail_route_reports_local_file_storage_metadata(statement_client, monkeypatch, tmp_path) -> None:
    client, _ = statement_client

    monkeypatch.setattr(statement_routes.get_settings(), "local_storage_path", str(tmp_path))

    upload_response = client.post(
        "/api/v1/statements/import-file",
        headers=actor_headers(),
        data={
            "telegram_user_id": "9001",
            "telegram_chat_id": "9001",
        },
        files={
            "file": (
                "halyk_statement.csv",
                b"date,amount,counterparty,description\n2026-08-10,150000,Client LLP,Client payment\n",
                "text/csv",
            )
        },
    )
    assert upload_response.status_code == 200
    imported_statement_id = upload_response.json()["imported_statement_id"]

    detail_response = client.get(
        f"/api/v1/statements/detail/{imported_statement_id}",
        headers=actor_headers(),
        params={"telegram_user_id": 9001},
    )

    assert detail_response.status_code == 200
    payload = detail_response.json()
    assert payload["imported_statement_id"] == imported_statement_id
    assert payload["storage_kind"] == "local_file"
    assert payload["file_available"] is True
    assert payload["original_filename"] == "halyk_statement.csv"
    assert payload["raw_line_count"] == 2
    assert payload["raw_preview"].startswith("date,amount,counterparty,description")


@pytest.mark.asyncio
async def test_statement_source_route_downloads_virtual_text_import(statement_client) -> None:
    client, _ = statement_client
    raw_text = "2026-08-10 Client LLP +150000\n2026-08-11 Arman T. -45000"

    import_response = client.post(
        "/api/v1/statements/import-text",
        headers=actor_headers(),
        json={
            "telegram_user_id": 9001,
            "telegram_chat_id": 9001,
            "raw_text": raw_text,
            "language": "en",
        },
    )
    assert import_response.status_code == 200
    imported_statement_id = import_response.json()["imported_statement_id"]

    source_response = client.get(
        f"/api/v1/statements/detail/{imported_statement_id}/source",
        headers=actor_headers(),
        params={"telegram_user_id": 9001, "language": "en"},
    )

    assert source_response.status_code == 200
    assert source_response.headers["content-type"].startswith("text/plain")
    assert "telegram_text_statement.txt" in source_response.headers["content-disposition"]
    assert source_response.text.strip() == raw_text


@pytest.mark.asyncio
async def test_statement_source_route_streams_uploaded_file(statement_client, monkeypatch, tmp_path) -> None:
    client, _ = statement_client

    monkeypatch.setattr(statement_routes.get_settings(), "local_storage_path", str(tmp_path))
    file_bytes = b"date,amount,counterparty,description\n2026-08-10,150000,Client LLP,Client payment\n"
    upload_response = client.post(
        "/api/v1/statements/import-file",
        headers=actor_headers(),
        data={
            "telegram_user_id": "9001",
            "telegram_chat_id": "9001",
        },
        files={
            "file": (
                "halyk_statement.csv",
                file_bytes,
                "text/csv",
            )
        },
    )
    assert upload_response.status_code == 200
    imported_statement_id = upload_response.json()["imported_statement_id"]

    source_response = client.get(
        f"/api/v1/statements/detail/{imported_statement_id}/source",
        headers=actor_headers(),
        params={"telegram_user_id": 9001},
    )

    assert source_response.status_code == 200
    assert source_response.headers["content-type"].startswith("text/csv")
    assert "halyk_statement.csv" in source_response.headers["content-disposition"]
    assert source_response.content == file_bytes


@pytest.mark.asyncio
async def test_statement_source_route_falls_back_to_raw_content_when_uploaded_file_is_missing(
    statement_client, monkeypatch, tmp_path
) -> None:
    client, _ = statement_client

    monkeypatch.setattr(statement_routes.get_settings(), "local_storage_path", str(tmp_path))
    file_text = "date,amount,counterparty,description\n2026-08-10,150000,Client LLP,Client payment\n"
    upload_response = client.post(
        "/api/v1/statements/import-file",
        headers=actor_headers(),
        data={
            "telegram_user_id": "9001",
            "telegram_chat_id": "9001",
        },
        files={
            "file": (
                "halyk_statement.csv",
                file_text.encode("utf-8"),
                "text/csv",
            )
        },
    )
    assert upload_response.status_code == 200
    imported_statement_id = upload_response.json()["imported_statement_id"]

    stored_files = list((tmp_path / "imports" / "webapp" / "statements").iterdir())
    assert len(stored_files) == 1
    stored_files[0].unlink()

    source_response = client.get(
        f"/api/v1/statements/detail/{imported_statement_id}/source",
        headers=actor_headers(),
        params={"telegram_user_id": 9001},
    )

    assert source_response.status_code == 200
    assert source_response.headers["content-type"].startswith("text/plain")
    assert "halyk_statement.txt" in source_response.headers["content-disposition"]
    assert source_response.text == file_text


@pytest.mark.asyncio
async def test_statement_workbench_route_returns_consistent_status_pending_and_history(statement_client) -> None:
    client, _ = statement_client
    language = "en"

    import_response = client.post(
        "/api/v1/statements/import-text",
        headers=actor_headers(),
        json={
            "telegram_user_id": 9001,
            "telegram_chat_id": 9001,
            "raw_text": "2026-08-10 Client LLP +150000\n2026-08-11 Arman T. -45000",
            "language": language,
        },
    )
    assert import_response.status_code == 200

    workbench_response = client.get(
        "/api/v1/statements/workbench",
        headers=actor_headers(),
        params={"telegram_user_id": 9001, "language": language, "limit": 5},
    )
    assert workbench_response.status_code == 200
    workbench_payload = workbench_response.json()
    assert workbench_payload["pending"] is not None
    assert workbench_payload["pending"]["current_index"] == 0
    assert workbench_payload["pending"]["remaining_count"] == 2
    assert workbench_payload["latest_status"]["parse_status"] == "clarification_required"
    assert workbench_payload["latest_status"]["remaining_clarifications"] == 2
    assert len(workbench_payload["history"]) == 1
    assert workbench_payload["history"][0]["remaining_clarifications"] == 2

    clarify_response = client.post(
        "/api/v1/statements/clarify",
        headers=actor_headers(),
        json={
            "telegram_user_id": 9001,
            "telegram_chat_id": 9001,
            "account_type": "business",
            "life_sector": "sales_income",
            "language": language,
        },
    )
    assert clarify_response.status_code == 200

    refreshed_workbench_response = client.get(
        "/api/v1/statements/workbench",
        headers=actor_headers(),
        params={"telegram_user_id": 9001, "language": language, "limit": 5},
    )
    assert refreshed_workbench_response.status_code == 200
    refreshed_payload = refreshed_workbench_response.json()
    assert refreshed_payload["pending"] is not None
    assert refreshed_payload["pending"]["current_index"] == 1
    assert refreshed_payload["pending"]["remaining_count"] == 1
    assert refreshed_payload["pending"]["prompt_message"].startswith(
        text("statement_prompt_intro", language, auto_count=0, ordinal=2, total=2)
    )
    assert refreshed_payload["latest_status"]["parse_status"] == "clarification_required"
    assert refreshed_payload["latest_status"]["remaining_clarifications"] == 1
    assert len(refreshed_payload["history"]) == 1
    assert refreshed_payload["history"][0]["remaining_clarifications"] == 1


@pytest.mark.asyncio
async def test_statement_routes_reject_new_import_while_clarification_is_active(statement_client) -> None:
    client, _ = statement_client
    language = "ru"

    first_import = client.post(
        "/api/v1/statements/import-text",
        headers=actor_headers(),
        json={
            "telegram_user_id": 9001,
            "telegram_chat_id": 9001,
            "raw_text": "2026-08-10 Client LLP +150000\n2026-08-11 Arman T. -45000",
            "language": language,
        },
    )
    assert first_import.status_code == 200

    conflict_response = client.post(
        "/api/v1/statements/import-text",
        headers=actor_headers(),
        json={
            "telegram_user_id": 9001,
            "telegram_chat_id": 9001,
            "raw_text": "2026-08-12 Kaspi Incoming +99000\n2026-08-13 Magnum -18250",
            "language": language,
        },
    )

    assert conflict_response.status_code == 409
    assert conflict_response.json()["detail"] == text(
        "statement_import_blocked",
        language,
        name="telegram_text_statement.txt",
        count=2,
    )


@pytest.mark.asyncio
async def test_statement_routes_cleanup_blocked_web_upload_file(statement_client, monkeypatch, tmp_path) -> None:
    client, _ = statement_client
    language = "ru"
    settings = get_settings()
    monkeypatch.setattr(settings, "local_storage_path", tmp_path, raising=False)

    first_import = client.post(
        "/api/v1/statements/import-text",
        headers=actor_headers(),
        json={
            "telegram_user_id": 9001,
            "telegram_chat_id": 9001,
            "raw_text": "2026-08-10 Client LLP +150000\n2026-08-11 Arman T. -45000",
            "language": language,
        },
    )
    assert first_import.status_code == 200

    conflict_response = client.post(
        "/api/v1/statements/import-file",
        headers=actor_headers(),
        data={
            "telegram_user_id": "9001",
            "telegram_chat_id": "9001",
            "language": language,
        },
        files={
            "file": (
                "blocked_statement.csv",
                "\n".join(
                    [
                        "date,amount,counterparty,description",
                        "2026-08-12,99000,Kaspi Incoming,Client settlement",
                        "2026-08-13,-18250,Magnum,Family groceries",
                    ]
                ).encode("utf-8"),
                "text/csv",
            )
        },
    )

    assert conflict_response.status_code == 409
    assert conflict_response.json()["detail"] == text(
        "statement_import_blocked",
        language,
        name="telegram_text_statement.txt",
        count=2,
    )
    upload_dir = tmp_path / "imports" / "webapp" / "statements"
    assert upload_dir.exists()
    assert list(upload_dir.iterdir()) == []


@pytest.mark.asyncio
async def test_statement_routes_cleanup_failed_web_upload_file(statement_client, monkeypatch, tmp_path) -> None:
    client, _ = statement_client
    language = "ru"
    settings = get_settings()
    monkeypatch.setattr(settings, "local_storage_path", tmp_path, raising=False)

    async def fail_import_file(self, **_kwargs):
        raise RuntimeError("Statement parser unavailable.")

    monkeypatch.setattr(statement_routes.StatementImportService, "import_file", fail_import_file)

    failed_response = client.post(
        "/api/v1/statements/import-file",
        headers=actor_headers(),
        data={
            "telegram_user_id": "9001",
            "telegram_chat_id": "9001",
            "language": language,
        },
        files={
            "file": (
                "failed_statement.csv",
                "\n".join(
                    [
                        "date,amount,counterparty,description",
                        "2026-08-12,99000,Kaspi Incoming,Client settlement",
                    ]
                ).encode("utf-8"),
                "text/csv",
            )
        },
    )

    assert failed_response.status_code == 503
    assert failed_response.json()["detail"] == text(
        "statement_import_failed",
        language,
        details="Statement parser unavailable.",
    )
    upload_dir = tmp_path / "imports" / "webapp" / "statements"
    assert upload_dir.exists()
    assert list(upload_dir.iterdir()) == []


@pytest.mark.asyncio
async def test_statement_routes_localize_unexpected_failed_web_upload_file(statement_client, monkeypatch, tmp_path) -> None:
    client, _ = statement_client
    language = "ru"
    settings = get_settings()
    monkeypatch.setattr(settings, "local_storage_path", tmp_path, raising=False)

    async def fail_import_file(self, **_kwargs):
        raise Exception("Unexpected classifier crash.")

    monkeypatch.setattr(statement_routes.StatementImportService, "import_file", fail_import_file)

    failed_response = client.post(
        "/api/v1/statements/import-file",
        headers=actor_headers(),
        data={
            "telegram_user_id": "9001",
            "telegram_chat_id": "9001",
            "language": language,
        },
        files={
            "file": (
                "failed_statement.csv",
                "\n".join(
                    [
                        "date,amount,counterparty,description",
                        "2026-08-12,99000,Kaspi Incoming,Client settlement",
                    ]
                ).encode("utf-8"),
                "text/csv",
            )
        },
    )

    assert failed_response.status_code == 500
    assert failed_response.json()["detail"] == text(
        "statement_import_failed",
        language,
        details="Unexpected classifier crash.",
    )
    upload_dir = tmp_path / "imports" / "webapp" / "statements"
    assert upload_dir.exists()
    assert list(upload_dir.iterdir()) == []


@pytest.mark.asyncio
async def test_statement_routes_localize_failed_text_import(statement_client, monkeypatch) -> None:
    client, _ = statement_client
    language = "ru"

    async def fail_import_text(self, **_kwargs):
        raise RuntimeError("Statement parser unavailable.")

    monkeypatch.setattr(statement_routes.StatementImportService, "import_text", fail_import_text)

    failed_response = client.post(
        "/api/v1/statements/import-text",
        headers=actor_headers(),
        json={
            "telegram_user_id": 9001,
            "telegram_chat_id": 9001,
            "raw_text": "2026-08-10 Client LLP +150000",
            "language": language,
        },
    )

    assert failed_response.status_code == 503
    assert failed_response.json()["detail"] == text(
        "statement_import_failed",
        language,
        details="Statement parser unavailable.",
    )


@pytest.mark.asyncio
async def test_statement_routes_localize_unexpected_failed_text_import(statement_client, monkeypatch) -> None:
    client, _ = statement_client
    language = "ru"

    async def fail_import_text(self, **_kwargs):
        raise Exception("Unexpected classifier crash.")

    monkeypatch.setattr(statement_routes.StatementImportService, "import_text", fail_import_text)

    failed_response = client.post(
        "/api/v1/statements/import-text",
        headers=actor_headers(),
        json={
            "telegram_user_id": 9001,
            "telegram_chat_id": 9001,
            "raw_text": "2026-08-10 Client LLP +150000",
            "language": language,
        },
    )

    assert failed_response.status_code == 500
    assert failed_response.json()["detail"] == text(
        "statement_import_failed",
        language,
        details="Unexpected classifier crash.",
    )


@pytest.mark.asyncio
async def test_statement_routes_reject_non_statement_text(statement_client) -> None:
    client, _ = statement_client
    language = "ru"

    response = client.post(
        "/api/v1/statements/import-text",
        headers=actor_headers(telegram_user_id=1, telegram_chat_id=1),
        json={
            "telegram_user_id": 1,
            "telegram_chat_id": 1,
            "raw_text": "hello team this is not a statement",
            "language": language,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == text("statement_text_not_recognized", language)


@pytest.mark.asyncio
async def test_statement_routes_reject_unsupported_statement_file(statement_client) -> None:
    client, _ = statement_client
    language = "ru"

    response = client.post(
        "/api/v1/statements/import-file",
        headers=actor_headers(),
        data={
            "telegram_user_id": "9001",
            "telegram_chat_id": "9001",
            "language": language,
        },
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == text("statement_file_type_unsupported", language)


@pytest.mark.asyncio
async def test_statement_routes_localize_invalid_clarification_payload(statement_client) -> None:
    client, _ = statement_client
    language = "ru"

    response = client.post(
        "/api/v1/statements/clarify",
        headers=actor_headers(),
        json={
            "telegram_user_id": 9001,
            "telegram_chat_id": 9001,
            "language": language,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == text("statement_clarification_payload_invalid", language)


@pytest.mark.asyncio
async def test_statement_routes_localize_no_pending_clarification(statement_client) -> None:
    client, _ = statement_client
    language = "ru"

    response = client.post(
        "/api/v1/statements/clarify",
        headers=actor_headers(),
        json={
            "telegram_user_id": 9001,
            "telegram_chat_id": 9001,
            "account_type": "business",
            "life_sector": "sales_income",
            "language": language,
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == text("statement_no_pending_for_user", language)


@pytest.mark.asyncio
async def test_statement_routes_refresh_stale_clarification_with_latest_status(statement_client) -> None:
    client, _ = statement_client
    language = "ru"

    import_response = client.post(
        "/api/v1/statements/import-text",
        headers=actor_headers(),
        json={
            "telegram_user_id": 9001,
            "telegram_chat_id": 9001,
            "raw_text": "2026-08-10 Client LLP +150000",
            "language": language,
        },
    )
    assert import_response.status_code == 200

    clarification_response = client.post(
        "/api/v1/statements/clarify",
        headers=actor_headers(),
        json={
            "telegram_user_id": 9001,
            "telegram_chat_id": 9001,
            "account_type": "business",
            "life_sector": "sales_income",
            "language": language,
        },
    )
    assert clarification_response.status_code == 200
    assert clarification_response.json()["latest_status"]["parse_status"] == "completed"

    stale_response = client.post(
        "/api/v1/statements/clarify",
        headers=actor_headers(),
        json={
            "telegram_user_id": 9001,
            "telegram_chat_id": 9001,
            "account_type": "business",
            "life_sector": "sales_income",
            "language": language,
        },
    )

    assert stale_response.status_code == 200
    payload = stale_response.json()
    assert payload["message"] == text("loaded_latest_statement_status", language)
    assert payload["pending"] is None
    assert payload["latest_status"]["parse_status"] == "completed"
    assert payload["latest_status"]["remaining_clarifications"] == 0
    assert payload["history"][0]["parse_status"] == "completed"
    assert payload["history"][0]["remaining_clarifications"] == 0


@pytest.mark.asyncio
async def test_statement_routes_localize_failed_clarification(statement_client, monkeypatch) -> None:
    client, _ = statement_client
    language = "ru"

    async def fail_clarification(self, **_kwargs):
        raise RuntimeError("Classifier unavailable.")

    monkeypatch.setattr(statement_routes.StatementImportService, "process_clarification_text", fail_clarification)

    response = client.post(
        "/api/v1/statements/clarify",
        headers=actor_headers(),
        json={
            "telegram_user_id": 9001,
            "telegram_chat_id": 9001,
            "answer_text": "business sales",
            "language": language,
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == text(
        "statement_clarification_failed",
        language,
        details="Classifier unavailable.",
    )


def test_statement_routes_reject_actor_mismatch(statement_client) -> None:
    client, _ = statement_client

    response = client.post(
        "/api/v1/statements/import-text",
        headers=actor_headers(telegram_user_id=9002, telegram_chat_id=9002),
        json={
            "telegram_user_id": 9001,
            "telegram_chat_id": 9001,
            "raw_text": "2026-08-10 Client LLP +150000",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Telegram actor does not match the requested telegram_user_id."


def test_statement_routes_read_workspace_uses_actor_identity_when_query_is_omitted(statement_client) -> None:
    client, _ = statement_client

    import_response = client.post(
        "/api/v1/statements/import-text",
        headers=actor_headers(),
        json={
            "telegram_user_id": 9001,
            "telegram_chat_id": 9001,
            "raw_text": "2026-08-10 Client LLP +150000",
            "language": "en",
        },
    )
    assert import_response.status_code == 200

    pending_response = client.get(
        "/api/v1/statements/pending",
        headers=actor_headers(),
        params={"language": "en"},
    )
    assert pending_response.status_code == 200
    pending_payload = pending_response.json()
    assert pending_payload is not None
    assert pending_payload["current_item"]["counterparty"] == "Client LLP"
    assert pending_payload["remaining_count"] == 1

    status_response = client.get(
        "/api/v1/statements/status",
        headers=actor_headers(),
        params={"language": "en"},
    )
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["pending"] is not None
    assert status_payload["pending"]["current_item"]["counterparty"] == "Client LLP"
    assert status_payload["latest_status"]["remaining_clarifications"] == 1

    history_response = client.get(
        "/api/v1/statements/history",
        headers=actor_headers(),
        params={"limit": 5},
    )
    assert history_response.status_code == 200
    history_payload = history_response.json()
    assert len(history_payload["items"]) == 1
    assert history_payload["items"][0]["remaining_clarifications"] == 1


def test_statement_routes_reject_family_member_role(statement_client) -> None:
    client, _ = statement_client

    response = client.post(
        "/api/v1/statements/import-text",
        headers=actor_headers(role="family_member"),
        json={
            "telegram_user_id": 9001,
            "telegram_chat_id": 9001,
            "raw_text": "2026-08-10 Client LLP +150000",
        },
    )

    assert response.status_code == 403
    assert "owner, cfo, coo, cashier" in response.json()["detail"]
