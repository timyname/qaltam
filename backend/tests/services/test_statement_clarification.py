from __future__ import annotations

from backend.app.services.statement_clarification import match_statement_clarification_choice


def test_match_statement_clarification_choice_accepts_spoken_ordinals_across_languages() -> None:
    item: dict[str, object] = {}

    first_choice = match_statement_clarification_choice("the first option please", item, lang="en")
    assert first_choice is not None
    assert first_choice.account_type == "business"
    assert first_choice.life_sector == "sales_income"

    second_choice = match_statement_clarification_choice("второй вариант", item, lang="ru")
    assert second_choice is not None
    assert second_choice.account_type == "business"
    assert second_choice.life_sector == "inventory_parts"

    kazakh_second_choice = match_statement_clarification_choice("екінші нұсқа", item, lang="kk")
    assert kazakh_second_choice is not None
    assert kazakh_second_choice.account_type == "business"
    assert kazakh_second_choice.life_sector == "inventory_parts"

    ukrainian_seventh_choice = match_statement_clarification_choice("сьомий варіант", item, lang="uk")
    assert ukrainian_seventh_choice is not None
    assert ukrainian_seventh_choice.account_type == "personal"
    assert ukrainian_seventh_choice.life_sector == "owner_draw"


def test_match_statement_clarification_choice_does_not_force_ordinal_from_mixed_reply() -> None:
    item: dict[str, object] = {}

    assert match_statement_clarification_choice("family one", item, lang="en") is None
