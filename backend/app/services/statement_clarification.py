from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping

from backend.app.localization import account_type_label, clarification_choice_label, life_sector_label, text
from backend.app.services.life_sectors import CLARIFICATION_BUTTON_CHOICES

CLARIFICATION_STOP_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "for",
    "from",
    "home",
    "i",
    "in",
    "is",
    "it",
    "its",
    "my",
    "of",
    "on",
    "or",
    "our",
    "private",
    "the",
    "this",
    "to",
    "was",
    "with",
    "в",
    "для",
    "до",
    "и",
    "из",
    "к",
    "личное",
    "личный",
    "мой",
    "моя",
    "на",
    "не",
    "по",
    "це",
    "і",
    "бул",
    "бұл",
    "жеке",
    "мен",
    "менин",
    "менің",
    "пен",
    "ушін",
    "үшін",
}

SAME_AS_BEFORE_ALIASES = {
    "same as before",
    "same before",
    "as before",
    "same as usual",
    "like before",
    "use previous",
    "previous one",
    "как раньше",
    "как и раньше",
    "как в прошлый раз",
    "как прошлый раз",
    "как обычно",
    "как всегда",
    "как до этого",
    "как раньше",
    "как обычно",
    "как в прошлый раз",
    "как прошлый раз",
    "как всегда",
    "как до этого",
    "как и раньше",
    "былтыргыдай",
    "бұрынғыдай",
    "алдындағыдай",
    "как и до этого",
    "як раніше",
    "як і раніше",
    "як завжди",
    "як минулого разу",
}

CHOICE_ACCOUNT_TYPE_TOKENS = {
    "business": {
        "business",
        "biz",
        "company",
        "work",
        "commercial",
        "office",
        "бизнес",
        "рабочее",
        "рабочий",
        "компания",
        "компании",
        "бизнес",
        "бизнеса",
        "бизнеске",
        "бизнесу",
        "бізнес",
        "компания",
        "компании",
        "компанию",
        "компанія",
        "рабочее",
        "рабочий",
        "жумыс",
        "жұмыс",
        "жұмысқа",
    },
    "personal": {
        "personal",
        "private",
        "family",
        "home",
        "self",
        "личное",
        "личный",
        "семья",
        "семье",
        "семьи",
        "частное",
        "дом",
        "личное",
        "личный",
        "частное",
        "семья",
        "семьи",
        "семье",
        "сімя",
        "дім",
        "дом",
        "жеке",
        "отбасы",
        "отбасына",
        "отбасыға",
        "особисте",
    },
}

CHOICE_LIFE_SECTOR_TOKENS = {
    "sales_income": {
        "sales",
        "sale",
        "income",
        "revenue",
        "client",
        "incoming",
        "payment",
        "продажа",
        "продажи",
        "доход",
        "выручка",
        "клиент",
        "оплата",
        "оплата",
        "выручка",
        "выручки",
        "клиента",
        "клиенту",
        "кіріс",
    },
    "inventory_parts": {
        "inventory",
        "parts",
        "part",
        "stock",
        "supplier",
        "suppliers",
        "purchase",
        "payment",
        "goods",
        "товар",
        "товары",
        "запчасти",
        "закуп",
        "закупка",
        "поставщик",
        "товар",
        "товара",
        "товаров",
        "товару",
        "товары",
        "запчасти",
        "запчасть",
        "поставщик",
        "поставщика",
        "поставщику",
        "поставка",
        "поставке",
        "поставку",
        "закупка",
        "закупки",
        "жабдық",
        "жабдыққа",
        "жабдықты",
        "тауар",
        "тауарға",
        "тауарды",
    },
    "rent_utilities": {
        "rent",
        "utility",
        "utilities",
        "office",
        "officeke",
        "аренда",
        "коммуналка",
        "офис",
        "аренда",
        "аренды",
        "коммуналка",
        "коммуналки",
        "коммуналку",
        "комуналка",
        "офиса",
        "офиске",
    },
    "taxes_fees": {"tax", "taxes", "fee", "fees", "налог", "налоги", "комиссия", "податок"},
    "family_living": {
        "family",
        "living",
        "food",
        "home",
        "household",
        "семья",
        "быт",
        "еда",
        "дом",
        "еда",
        "еды",
        "семья",
        "семьи",
        "семье",
        "отбасы",
        "отбасына",
        "отбасыға",
    },
    "savings_debt": {"savings", "saving", "debt", "loan", "credit", "reserve", "накопления", "долг", "борг"},
    "owner_draw": {"owner", "draw", "withdraw", "withdrawal", "self", "ownerpay", "владелец", "дивиденд", "алу"},
}

ORDINAL_REFERENCE_NOISE_TOKENS = {
    *CLARIFICATION_STOP_WORDS,
    "answer",
    "choice",
    "choices",
    "number",
    "option",
    "options",
    "please",
    "pls",
    "plz",
    "reply",
    "variant",
    "variants",
    "пж",
    "пожалуйста",
    "будь",
    "ласка",
    "вариант",
    "варианта",
    "вариантом",
    "варианты",
    "отинемин",
    "өтінемін",
    "жауап",
    "жауабы",
    "жауапты",
    "нуска",
    "нұсқа",
    "нұсқаны",
    "нұсқасы",
    "таңдау",
    "таңдауы",
    "варианту",
    "варіант",
    "варіанти",
    "відповідь",
    "відповіді",
}


@dataclass(frozen=True, slots=True)
class StatementClarificationChoice:
    label: str
    account_type: str
    life_sector: str
    is_suggested: bool = False
    is_learned: bool = False


def ordered_statement_clarification_choices(
    item: Mapping[str, object] | None,
    *,
    lang: str = "ru",
) -> list[StatementClarificationChoice]:
    choices: list[StatementClarificationChoice] = []
    seen: set[tuple[str, str]] = set()

    matched_rules = item.get("matched_rules") if item else None
    for rule in matched_rules if isinstance(matched_rules, list) else []:
        account_type = _clean_value(rule.get("account_type")) if isinstance(rule, Mapping) else None
        life_sector = _clean_value(rule.get("life_sector")) if isinstance(rule, Mapping) else None
        if not account_type or not life_sector:
            continue
        key = (account_type, life_sector)
        if key in seen:
            continue
        seen.add(key)
        choices.append(
            StatementClarificationChoice(
                label=text(
                    "learned_choice",
                    lang,
                    account_type=account_type_label(account_type, lang),
                    life_sector=life_sector_label(life_sector, lang),
                ),
                account_type=account_type,
                life_sector=life_sector,
                is_learned=True,
            )
        )

    suggested_account_type = _clean_value(item.get("suggested_account_type")) if item else None
    suggested_life_sector = _clean_value(item.get("suggested_life_sector")) if item else None
    if suggested_account_type and suggested_life_sector:
        key = (suggested_account_type, suggested_life_sector)
        if key not in seen:
            seen.add(key)
            choices.append(
                StatementClarificationChoice(
                    label=text(
                        "suggested_choice",
                        lang,
                        account_type=account_type_label(suggested_account_type, lang),
                        life_sector=life_sector_label(suggested_life_sector, lang),
                    ),
                    account_type=suggested_account_type,
                    life_sector=suggested_life_sector,
                    is_suggested=True,
                )
            )

    for _display_label, account_type, life_sector in CLARIFICATION_BUTTON_CHOICES:
        key = (account_type, life_sector)
        if key in seen:
            continue
        seen.add(key)
        choices.append(
            StatementClarificationChoice(
                label=clarification_choice_label(account_type, life_sector, lang),
                account_type=account_type,
                life_sector=life_sector,
            )
        )

    return choices


def match_statement_clarification_choice(
    answer_text: str,
    item: Mapping[str, object] | None,
    *,
    lang: str = "ru",
) -> StatementClarificationChoice | None:
    normalized_answer = _normalize_phrase(answer_text)
    if not normalized_answer:
        return None

    choices = ordered_statement_clarification_choices(item, lang=lang)
    indexed_choice = _indexed_choice_from_reference(normalized_answer, choices, lang=lang)
    if indexed_choice:
        return indexed_choice

    tokens = normalized_answer.split()

    same_as_before_choice = _same_as_before_choice(normalized_answer, item, lang=lang)
    if same_as_before_choice:
        return same_as_before_choice

    for choice in choices:
        if normalized_answer in _choice_aliases(choice):
            return choice
        if _matches_choice_tokens(tokens, choice, lang=lang):
            return choice

    return None


def render_statement_clarification_choices(
    item: Mapping[str, object] | None,
    *,
    lang: str = "ru",
) -> str:
    choices = ordered_statement_clarification_choices(item, lang=lang)
    if not choices:
        return ""

    lines = [text("statement_quick_choices_intro", lang)]
    for index, choice in enumerate(choices, start=1):
        lines.append(f"{index}. {choice.label}")
    return "\n".join(lines)


def _choice_aliases(choice: StatementClarificationChoice) -> set[str]:
    aliases = {
        _normalize_phrase(choice.label),
        _normalize_phrase(clarification_choice_label(choice.account_type, choice.life_sector)),
        _normalize_phrase(f"{choice.account_type} {choice.life_sector.replace('_', ' ')}"),
        _normalize_phrase(choice.life_sector.replace("_", " ")),
    }
    aliases.discard("")
    return aliases


def _same_as_before_choice(
    normalized_answer: str,
    item: Mapping[str, object] | None,
    *,
    lang: str = "ru",
) -> StatementClarificationChoice | None:
    if normalized_answer not in SAME_AS_BEFORE_ALIASES or not item:
        return None

    matched_rules = item.get("matched_rules")
    for rule in matched_rules if isinstance(matched_rules, list) else []:
        account_type = _clean_value(rule.get("account_type")) if isinstance(rule, Mapping) else None
        life_sector = _clean_value(rule.get("life_sector")) if isinstance(rule, Mapping) else None
        if not account_type or not life_sector:
            continue
        return StatementClarificationChoice(
            label=text(
                "learned_choice",
                lang,
                account_type=account_type_label(account_type, lang),
                life_sector=life_sector_label(life_sector, lang),
            ),
            account_type=account_type,
            life_sector=life_sector,
            is_learned=True,
        )

    suggested_account_type = _clean_value(item.get("suggested_account_type"))
    suggested_life_sector = _clean_value(item.get("suggested_life_sector"))
    if suggested_account_type and suggested_life_sector:
        return StatementClarificationChoice(
            label=text(
                "suggested_choice",
                lang,
                account_type=account_type_label(suggested_account_type, lang),
                life_sector=life_sector_label(suggested_life_sector, lang),
            ),
            account_type=suggested_account_type,
            life_sector=suggested_life_sector,
            is_suggested=True,
        )

    return None


def _indexed_choice_from_reference(
    normalized_answer: str,
    choices: list[StatementClarificationChoice],
    *,
    lang: str = "ru",
) -> StatementClarificationChoice | None:
    if not choices:
        return None

    direct_index = _spoken_ordinal_index(normalized_answer, max_index=len(choices))
    if direct_index is not None:
        return choices[direct_index - 1]

    tokens = normalized_answer.split()
    if not tokens:
        return None

    prefixed_index = _single_token_ordinal_index(tokens[0], max_index=len(choices))
    if prefixed_index is None:
        return None

    indexed_choice = choices[prefixed_index - 1]
    if len(tokens) == 1 or _matches_choice_tokens(tokens[1:], indexed_choice, lang=lang):
        return indexed_choice
    return None


def _matches_choice_tokens(tokens: list[str], choice: StatementClarificationChoice, *, lang: str = "ru") -> bool:
    content_tokens = [token for token in tokens if token and token not in CLARIFICATION_STOP_WORDS]
    if not content_tokens:
        return False

    choice_tokens = _choice_tokens(choice, lang=lang)
    return all(token in choice_tokens for token in content_tokens)


def _choice_tokens(choice: StatementClarificationChoice, *, lang: str = "ru") -> set[str]:
    tokens = set()
    tokens.update(_choice_alias_tokens(choice.label))
    tokens.update(_choice_alias_tokens(clarification_choice_label(choice.account_type, choice.life_sector, lang)))
    tokens.update(_choice_alias_tokens(account_type_label(choice.account_type, lang)))
    tokens.update(_choice_alias_tokens(life_sector_label(choice.life_sector, lang)))
    tokens.update(_choice_alias_tokens(choice.account_type))
    tokens.update(_choice_alias_tokens(choice.life_sector.replace("_", " ")))
    tokens.update(CHOICE_ACCOUNT_TYPE_TOKENS.get(choice.account_type, set()))
    tokens.update(CHOICE_LIFE_SECTOR_TOKENS.get(choice.life_sector, set()))
    tokens.discard("")
    return tokens


def _choice_alias_tokens(value: str) -> set[str]:
    return {token for token in _normalize_phrase(value).split() if token}


def _spoken_ordinal_index(value: str, *, max_index: int | None = None) -> int | None:
    normalized_value = _normalize_phrase(value)
    if not normalized_value:
        return None

    direct_index = _single_token_ordinal_index(normalized_value, max_index=max_index)
    if direct_index is not None:
        return direct_index

    alias_index = _ordinal_reference_aliases().get(normalized_value)
    if alias_index is not None and _ordinal_index_within_limit(alias_index, max_index=max_index):
        return alias_index

    trimmed_tokens = [token for token in normalized_value.split() if token not in ORDINAL_REFERENCE_NOISE_TOKENS]
    if not trimmed_tokens:
        return None

    trimmed_value = " ".join(trimmed_tokens)
    trimmed_index = _single_token_ordinal_index(trimmed_value, max_index=max_index)
    if trimmed_index is not None:
        return trimmed_index

    alias_index = _ordinal_reference_aliases().get(trimmed_value)
    if alias_index is not None and _ordinal_index_within_limit(alias_index, max_index=max_index):
        return alias_index

    matches = {_single_token_ordinal_index(token, max_index=max_index) for token in trimmed_tokens}
    matches.discard(None)
    if len(matches) == 1 and len(matches) == len(trimmed_tokens):
        return next(iter(matches))
    return None


def _single_token_ordinal_index(value: str, *, max_index: int | None = None) -> int | None:
    direct_match = re.fullmatch(r"(\d+)(?:st|nd|rd|th)?", value)
    if direct_match:
        index = int(direct_match.group(1))
        if _ordinal_index_within_limit(index, max_index=max_index):
            return index

    alias_index = _ordinal_reference_aliases().get(value)
    if alias_index is not None and _ordinal_index_within_limit(alias_index, max_index=max_index):
        return alias_index
    return None


def _ordinal_index_within_limit(index: int, *, max_index: int | None = None) -> bool:
    if index < 1:
        return False
    if max_index is not None and index > max_index:
        return False
    return True


def _ordinal_reference_aliases() -> dict[str, int]:
    raw_aliases = {
        1: {
            "1st",
            "first",
            "one",
            "number one",
            "first one",
            "первый",
            "первая",
            "первую",
            "один",
            "одна",
            "одну",
            "бірінші",
            "бір",
            "перший",
            "перша",
            "першу",
        },
        2: {
            "2nd",
            "second",
            "two",
            "number two",
            "second one",
            "второй",
            "вторая",
            "вторую",
            "два",
            "две",
            "екінші",
            "екі",
            "другий",
            "друга",
            "другу",
            "дві",
        },
        3: {
            "3rd",
            "third",
            "three",
            "number three",
            "third one",
            "третий",
            "третья",
            "третью",
            "три",
            "үшінші",
            "үш",
            "третій",
            "третя",
            "третю",
        },
        4: {
            "4th",
            "fourth",
            "four",
            "number four",
            "fourth one",
            "четвертый",
            "четвертая",
            "четвертую",
            "четыре",
            "төртінші",
            "төрт",
            "четвертий",
            "четверта",
            "четверту",
            "чотири",
        },
        5: {
            "5th",
            "fifth",
            "five",
            "number five",
            "fifth one",
            "пятый",
            "пятая",
            "пятую",
            "пять",
            "бесінші",
            "бес",
            "пятий",
            "п'ятий",
            "пята",
            "пяту",
        },
        6: {
            "6th",
            "sixth",
            "six",
            "number six",
            "sixth one",
            "шестой",
            "шестая",
            "шестую",
            "шесть",
            "алтыншы",
            "алты",
            "шостий",
            "шоста",
            "шосту",
            "шість",
        },
        7: {
            "7th",
            "seventh",
            "seven",
            "number seven",
            "seventh one",
            "седьмой",
            "седьмая",
            "седьмую",
            "семь",
            "жетінші",
            "жеті",
            "сьомий",
            "сьома",
            "сьому",
            "сім",
        },
    }
    aliases: dict[str, int] = {}
    for index, values in raw_aliases.items():
        for value in values:
            normalized = _normalize_phrase(value)
            if normalized:
                aliases[normalized] = index
    return aliases


def _normalize_phrase(value: str) -> str:
    return " ".join(
        token for token in (_normalize_token(token) for token in re.findall(r"[\w/-]+", value, flags=re.UNICODE)) if token
    )


def _normalize_token(value: str) -> str:
    return value.casefold().strip(" ./_-")


def _clean_value(value: object | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
