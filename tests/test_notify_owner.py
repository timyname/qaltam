import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "notify_owner.py"


def load_module():
    spec = importlib.util.spec_from_file_location("notify_owner", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_message_matches_requested_copy():
    module = load_module()

    assert module.build_message() == (
        "📂 All QALTAM files have been consolidated into the `./qaltam` folder!\n"
        "✅ Backend & Frontend tests passed inside `./qaltam`.\n"
        "🐳 Ready to launch: `cd qaltam && docker-compose up --build -d`"
    )


def test_find_chat_id_in_updates_matches_owner_username_case_insensitively():
    module = load_module()
    updates = [
        {
            "update_id": 1,
            "message": {
                "from": {"id": 555, "username": "SomeoneElse"},
                "chat": {"id": 555, "type": "private", "username": "SomeoneElse"},
            },
        },
        {
            "update_id": 2,
            "message": {
                "from": {"id": 777, "username": "AsProYant"},
                "chat": {"id": 777, "type": "private", "username": "AsProYant"},
            },
        },
    ]

    assert module.find_chat_id_in_updates(updates, "@asproyant") == 777


def test_resolve_chat_id_prefers_explicit_override():
    module = load_module()

    assert module.resolve_chat_id("998877", "@asproyant", []) == 998877


def test_load_report_text_reads_utf8_markdown_file(tmp_path):
    module = load_module()
    report_path = tmp_path / "owner-report.md"
    report_path.write_text("Line 1\nLine 2\n", encoding="utf-8")

    assert module.load_report_text(str(report_path)) == "Line 1\nLine 2"


def test_coerce_console_text_replaces_unencodable_characters_for_cp1251():
    module = load_module()

    assert module.coerce_console_text("📂 QALTAM", "cp1251") == "? QALTAM"
