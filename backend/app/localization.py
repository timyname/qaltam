from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.profile import UserProfile


SUPPORTED_LANGUAGES = {"ru", "kk", "en", "uk"}
LANGUAGE_ALIASES = {
    "kz": "kk",
}

TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        "open_app": "Open QALTAM / FOCUS",
        "review_in_app": "Review in QALTAM / FOCUS",
        "review_receipt_lane": "Review receipt lane",
        "app_launcher_message": "Open the QALTAM / FOCUS Mini App to review cashflow, bridge sectors, and pending clarifications.",
        "invalid_action": "Invalid action",
        "unsupported_action": "Unsupported statement action.",
        "saved": "Saved",
        "no_statement_imports_yet": "No statement imports yet.",
        "loaded_latest_statement_status": "Loaded latest statement status",
        "loaded_recent_statement_imports": "Loaded recent statement imports",
        "refreshed_active_clarification": "Refreshed active clarification",
        "no_pending_statement_clarification_alert": "No pending statement clarification.",
        "refresh_active_statement": "Refresh active statement",
        "latest_statement_status": "Latest statement status",
        "recent_statement_imports": "Recent statement imports",
        "resume_clarification": "Resume clarification",
        "suggested_choice": "Suggested: {account_type} / {life_sector}",
        "learned_choice": "Learned: {account_type} / {life_sector}",
        "help_line_1": "Send a bank statement as PDF, CSV, XLSX, or XLS, or paste raw statement lines here.",
        "help_line_2": "Use /clarify any time to resume the current clarification loop.",
        "help_line_3": "Use /app or the Mini App button below to inspect balances, cashflow, and pending questions.",
        "recent_statement_imports_title": "Recent statement imports:",
        "active_clarification_queue": "Active clarification queue: {count} still open",
        "history_shortcuts": (
            "Reply `detail 1` to open an import or `source 1` to receive its original file. "
            "You can also use the buttons below."
        ),
        "history_footer": "Use /clarify to jump back into the active queue, or open the Mini App for the full workbench.",
        "active_statement": "Active statement: {name}",
        "resolved_so_far": "Resolved so far: {count}",
        "remaining_clarifications": "Remaining clarifications: {count}",
        "no_pending_statement_clarifications": "No pending statement clarifications right now.",
        "completed_statement_footer": "Use the buttons below to review status or open the Mini App.",
        "latest_statement": "Latest statement: {name}",
        "source": "Source: {value}",
        "imported": "Imported: {value}",
        "status": "Status: {value}",
        "parsed_items": "Parsed items: {count}",
        "auto_categorized": "Auto-categorized: {count}",
        "needs_clarification": "Needs clarification: {count}",
        "history_item_status": "Status: {value}",
        "history_item_imported": "Imported: {value}",
        "history_item_parsed": "Parsed: {count}",
        "history_item_auto": "Auto: {count}",
        "history_item_open_clarifications": "Open clarifications: {count}",
        "unsupported_statement_document": "This document format is not supported for bank statement import yet. Send PDF, CSV, XLSX, or XLS, or paste raw statement lines here.",
        "statement_import_failed": "Could not import this statement right now. Send PDF, CSV, XLSX, or XLS, or paste raw statement lines here. Details: {details}",
        "statement_import_blocked": 'Finish the active clarification for "{name}" before importing a new statement. Remaining clarifications: {count}.',
        "statement_text_not_recognized": "Text does not look like a bank statement.",
        "statement_file_required": "Statement file is required.",
        "statement_file_type_unsupported": "Unsupported statement file type. Use PDF, CSV, XLSX, or XLS.",
        "statement_file_empty": "Uploaded statement file is empty.",
        "statement_clarification_failed": "Could not save this clarification right now. Please try again. Details: {details}",
        "statement_clarification_payload_invalid": "Provide either answer_text or account_type with life_sector.",
        "statement_no_pending_for_user": "No pending statement clarification for this Telegram user.",
        "voice_clarification_unavailable": "Voice clarification is unavailable locally right now. Please reply in text or install the local speech stack. Details: {details}",
        "statement_status_completed": "Completed",
        "statement_status_clarification_required": "Clarification Required",
        "statement_status_processing": "Processing",
        "statement_status_failed": "Failed",
        "account_type_business": "Business",
        "account_type_personal": "Personal",
        "life_sector_sales_income": "Sales / Income",
        "life_sector_inventory_parts": "Inventory / Parts",
        "life_sector_payroll_team": "Payroll / Team",
        "life_sector_rent_utilities": "Rent / Utilities",
        "life_sector_logistics_transport": "Logistics / Transport",
        "life_sector_marketing_growth": "Marketing / Growth",
        "life_sector_taxes_fees": "Taxes / Fees",
        "life_sector_tools_software": "Tools / Software",
        "life_sector_owner_draw": "Owner Draw",
        "life_sector_family_living": "Family / Living",
        "life_sector_savings_debt": "Savings / Debt",
        "chat_logged": "Logged: {category} {amount}",
        "chat_need_clarification": "Got it. Clarify whether this is an expense, income, or goal?",
        "photo_recognized": "Receipt recognized: {category} {amount}",
        "photo_not_recognized": "Could not recognize the receipt. Try again.",
        "receipt_saved": "Receipt saved: {merchant} {amount}. SKU: {sku_count}. Top items: {top_items}.",
        "voice_logged": "Logged by voice: {category} {amount}",
        "voice_not_recognized": "Could not recognize the voice note. Try again.",
    },
    "ru": {
        "open_app": "Открыть QALTAM / FOCUS",
        "review_in_app": "Открыть в QALTAM / FOCUS",
        "review_receipt_lane": "Открыть чековую ленту",
        "app_launcher_message": "Открой Mini App QALTAM / FOCUS, чтобы посмотреть кешфлоу, мосты заботы и открытые уточнения.",
        "invalid_action": "Некорректное действие",
        "unsupported_action": "Это действие по выписке не поддерживается.",
        "saved": "Сохранено",
        "no_statement_imports_yet": "Импортов выписок пока нет.",
        "loaded_latest_statement_status": "Загрузил статус последней выписки",
        "loaded_recent_statement_imports": "Загрузил последние импорты выписок",
        "refreshed_active_clarification": "Обновил активное уточнение",
        "no_pending_statement_clarification_alert": "Сейчас нет активных уточнений по выписке.",
        "refresh_active_statement": "Обновить активную выписку",
        "latest_statement_status": "Статус последней выписки",
        "recent_statement_imports": "Последние импорты выписок",
        "resume_clarification": "Продолжить уточнение",
        "suggested_choice": "Подсказка: {account_type} / {life_sector}",
        "learned_choice": "Из памяти: {account_type} / {life_sector}",
        "help_line_1": "Отправь банковскую выписку в формате PDF, CSV, XLSX или XLS, либо вставь строки выписки прямо сюда.",
        "help_line_2": "Используй /clarify в любой момент, чтобы продолжить текущий цикл уточнений.",
        "help_line_3": "Используй /app или кнопку Mini App ниже, чтобы посмотреть балансы, кешфлоу и открытые вопросы.",
        "recent_statement_imports_title": "Последние импорты выписок:",
        "active_clarification_queue": "В активной очереди уточнений осталось: {count}",
        "history_shortcuts": (
            "Ответь `detail 1`, чтобы открыть импорт, или `source 1`, чтобы получить исходный файл. "
            "Можно также нажать кнопки ниже."
        ),
        "history_footer": "Используй /clarify, чтобы вернуться в активную очередь, или открой Mini App для полного рабочего стола.",
        "active_statement": "Активная выписка: {name}",
        "resolved_so_far": "Уже разобрано: {count}",
        "remaining_clarifications": "Осталось уточнений: {count}",
        "no_pending_statement_clarifications": "Сейчас нет активных уточнений по выписке.",
        "completed_statement_footer": "Используй кнопки ниже, чтобы открыть статус или перейти в Mini App.",
        "latest_statement": "Последняя выписка: {name}",
        "source": "Источник: {value}",
        "imported": "Импортировано: {value}",
        "status": "Статус: {value}",
        "parsed_items": "Разобрано строк: {count}",
        "auto_categorized": "Автокатегоризовано: {count}",
        "needs_clarification": "Нужно уточнить: {count}",
        "history_item_status": "Статус: {value}",
        "history_item_imported": "Импортировано: {value}",
        "history_item_parsed": "Разобрано: {count}",
        "history_item_auto": "Авто: {count}",
        "history_item_open_clarifications": "Открытых уточнений: {count}",
        "unsupported_statement_document": "Этот формат документа пока не поддерживается для импорта банковской выписки. Отправь PDF, CSV, XLSX или XLS, либо вставь строки выписки прямо сюда.",
        "statement_import_failed": "Не получилось импортировать эту выписку прямо сейчас. Отправь PDF, CSV, XLSX или XLS, либо вставь строки выписки прямо сюда. Детали: {details}",
        "statement_text_not_recognized": "Текст не похож на банковскую выписку.",
        "statement_file_required": "Нужен файл выписки.",
        "statement_file_type_unsupported": "Формат файла выписки не поддерживается. Используй PDF, CSV, XLSX или XLS.",
        "statement_file_empty": "Загруженный файл выписки пуст.",
        "statement_clarification_payload_invalid": "Передай либо answer_text, либо account_type вместе с life_sector.",
        "statement_no_pending_for_user": "Для этого Telegram-пользователя нет ожидающих уточнений по выписке.",
        "voice_clarification_unavailable": "Локальное голосовое уточнение сейчас недоступно. Ответь текстом или установи локальный speech stack. Детали: {details}",
        "statement_status_completed": "Завершено",
        "statement_status_clarification_required": "Нужно уточнение",
        "statement_status_processing": "Обработка",
        "statement_status_failed": "Ошибка",
        "account_type_business": "Бизнес",
        "account_type_personal": "Личное",
        "life_sector_sales_income": "Продажи / Доход",
        "life_sector_inventory_parts": "Товар / Запчасти",
        "life_sector_payroll_team": "Команда / Зарплата",
        "life_sector_rent_utilities": "Аренда / Коммуналка",
        "life_sector_logistics_transport": "Логистика / Транспорт",
        "life_sector_marketing_growth": "Маркетинг / Рост",
        "life_sector_taxes_fees": "Налоги / Сборы",
        "life_sector_tools_software": "Инструменты / Софт",
        "life_sector_owner_draw": "Вывод владельца",
        "life_sector_family_living": "Семья / Быт",
        "life_sector_savings_debt": "Сбережения / Долги",
        "chat_logged": "Записал: {category} {amount}",
        "chat_need_clarification": "Принял. Уточни, это трата, поступление или цель?",
        "photo_recognized": "Чек распознан: {category} {amount}",
        "photo_not_recognized": "Не удалось распознать чек. Попробуй еще раз.",
        "receipt_saved": "Чек сохранен: {merchant} {amount}. SKU: {sku_count}. Топ позиции: {top_items}.",
        "voice_logged": "Записал по голосу: {category} {amount}",
        "voice_not_recognized": "Не смог распознать голос. Попробуй еще раз.",
    },
    "kk": {
        "open_app": "QALTAM / FOCUS ашу",
        "review_in_app": "QALTAM / FOCUS ішінде қарау",
        "review_receipt_lane": "Чек жолағын ашу",
        "app_launcher_message": "Кэшфлоу, қамқорлық көпірлері және ашық нақтылауларды көру үшін QALTAM / FOCUS Mini App-ты аш.",
        "invalid_action": "Қате әрекет",
        "unsupported_action": "Бұл үзінді әрекеті қолдау таппайды.",
        "saved": "Сақталды",
        "no_statement_imports_yet": "Үзінді импорттары әлі жоқ.",
        "loaded_latest_statement_status": "Соңғы үзіндінің күйі жүктелді",
        "loaded_recent_statement_imports": "Соңғы үзінді импорттары жүктелді",
        "refreshed_active_clarification": "Белсенді нақтылау жаңартылды",
        "no_pending_statement_clarification_alert": "Қазір үзінді бойынша белсенді нақтылау жоқ.",
        "refresh_active_statement": "Белсенді үзіндіні жаңарту",
        "latest_statement_status": "Соңғы үзіндінің күйі",
        "recent_statement_imports": "Соңғы үзінді импорттары",
        "resume_clarification": "Нақтылауды жалғастыру",
        "suggested_choice": "Ұсыныс: {account_type} / {life_sector}",
        "learned_choice": "Есте сақталғаны: {account_type} / {life_sector}",
        "help_line_1": "Банк үзіндісін PDF, CSV, XLSX немесе XLS форматында жібер, не жолдарын осында қой.",
        "help_line_2": "/clarify пәрменін кез келген уақытта қолданып, ағымдағы нақтылау циклін жалғастыр.",
        "help_line_3": "Баланс, кэшфлоу және ашық сұрақтарды көру үшін /app не төмендегі Mini App батырмасын қолдан.",
        "recent_statement_imports_title": "Соңғы үзінді импорттары:",
        "active_clarification_queue": "Белсенді нақтылау кезегінде қалды: {count}",
        "history_shortcuts": (
            "`detail 1` деп жауап беріп импортты аш немесе `source 1` деп жазып бастапқы файлды ал. "
            "Төмендегі батырмаларды да қолдануға болады."
        ),
        "history_footer": "Белсенді кезекке қайта кіру үшін /clarify қолдан немесе толық workbench үшін Mini App аш.",
        "active_statement": "Белсенді үзінді: {name}",
        "resolved_so_far": "Шешілгені: {count}",
        "remaining_clarifications": "Қалған нақтылаулар: {count}",
        "no_pending_statement_clarifications": "Қазір үзінді бойынша белсенді нақтылау жоқ.",
        "completed_statement_footer": "Күйді көру не Mini App ашу үшін төмендегі батырмаларды қолдан.",
        "latest_statement": "Соңғы үзінді: {name}",
        "source": "Дереккөз: {value}",
        "imported": "Импорт уақыты: {value}",
        "status": "Күйі: {value}",
        "parsed_items": "Талданған жолдар: {count}",
        "auto_categorized": "Авто санатталғаны: {count}",
        "needs_clarification": "Нақтылау керек: {count}",
        "history_item_status": "Күйі: {value}",
        "history_item_imported": "Импорт: {value}",
        "history_item_parsed": "Талданды: {count}",
        "history_item_auto": "Авто: {count}",
        "history_item_open_clarifications": "Ашық нақтылаулар: {count}",
        "unsupported_statement_document": "Бұл құжат форматы банк үзіндісін импорттауға әлі қолдау таппайды. PDF, CSV, XLSX немесе XLS жібер, не жолдарын осында қой.",
        "statement_import_failed": "Бұл үзіндіні қазір импорттау мүмкін болмады. PDF, CSV, XLSX немесе XLS жібер, не жолдарын осында қой. Толығырақ: {details}",
        "statement_text_not_recognized": "Мәтін банк үзіндісіне ұқсамайды.",
        "statement_file_required": "Үзінді файлы қажет.",
        "statement_file_type_unsupported": "Үзінді файлының форматына қолдау жоқ. PDF, CSV, XLSX немесе XLS қолдан.",
        "statement_file_empty": "Жүктелген үзінді файлы бос.",
        "statement_clarification_payload_invalid": "Не answer_text, не account_type пен life_sector бірге жібер.",
        "statement_no_pending_for_user": "Бұл Telegram пайдаланушысы үшін күтіліп тұрған үзінді нақтылауы жоқ.",
        "voice_clarification_unavailable": "Жергілікті дауыстық нақтылау қазір қолжетімсіз. Мәтінмен жауап бер немесе жергілікті speech stack орнат. Толығырақ: {details}",
        "statement_status_completed": "Аяқталды",
        "statement_status_clarification_required": "Нақтылау қажет",
        "statement_status_processing": "Өңделуде",
        "statement_status_failed": "Қате",
        "account_type_business": "Бизнес",
        "account_type_personal": "Жеке",
        "life_sector_sales_income": "Сату / Табыс",
        "life_sector_inventory_parts": "Қор / Бөлшек",
        "life_sector_payroll_team": "Команда / Жалақы",
        "life_sector_rent_utilities": "Жалдау / Коммуналдық",
        "life_sector_logistics_transport": "Логистика / Көлік",
        "life_sector_marketing_growth": "Маркетинг / Өсу",
        "life_sector_taxes_fees": "Салық / Төлем",
        "life_sector_tools_software": "Құрал / Софт",
        "life_sector_owner_draw": "Иесінің алуы",
        "life_sector_family_living": "Отбасы / Тұрмыс",
        "life_sector_savings_debt": "Жинақ / Қарыз",
        "chat_logged": "Жазылды: {category} {amount}",
        "chat_need_clarification": "Қабылдадым. Бұл шығын ба, кіріс пе, әлде мақсат па?",
        "photo_recognized": "Чек танылды: {category} {amount}",
        "photo_not_recognized": "Чекті тану мүмкін болмады. Қайта көр.",
        "receipt_saved": "Чек сақталды: {merchant} {amount}. SKU: {sku_count}. Негізгі позициялар: {top_items}.",
        "voice_logged": "Дауыс арқылы жазылды: {category} {amount}",
        "voice_not_recognized": "Дауысты тану мүмкін болмады. Қайта көр.",
    },
    "uk": {
        "open_app": "Відкрити QALTAM / FOCUS",
        "review_in_app": "Переглянути в QALTAM / FOCUS",
        "review_receipt_lane": "Відкрити стрічку чеків",
        "app_launcher_message": "Відкрий Mini App QALTAM / FOCUS, щоб переглянути кешфлоу, мости турботи та відкриті уточнення.",
        "invalid_action": "Некоректна дія",
        "unsupported_action": "Ця дія для виписки не підтримується.",
        "saved": "Збережено",
        "no_statement_imports_yet": "Імпортів виписок ще немає.",
        "loaded_latest_statement_status": "Завантажено статус останньої виписки",
        "loaded_recent_statement_imports": "Завантажено останні імпорти виписок",
        "refreshed_active_clarification": "Активне уточнення оновлено",
        "no_pending_statement_clarification_alert": "Зараз немає активних уточнень по виписці.",
        "refresh_active_statement": "Оновити активну виписку",
        "latest_statement_status": "Статус останньої виписки",
        "recent_statement_imports": "Останні імпорти виписок",
        "resume_clarification": "Продовжити уточнення",
        "suggested_choice": "Підказка: {account_type} / {life_sector}",
        "learned_choice": "З пам'яті: {account_type} / {life_sector}",
        "help_line_1": "Надішли банківську виписку у форматі PDF, CSV, XLSX або XLS, або встав рядки виписки сюди.",
        "help_line_2": "Використовуй /clarify у будь-який момент, щоб продовжити поточний цикл уточнень.",
        "help_line_3": "Використовуй /app або кнопку Mini App нижче, щоб переглянути баланси, кешфлоу та відкриті питання.",
        "recent_statement_imports_title": "Останні імпорти виписок:",
        "active_clarification_queue": "В активній черзі уточнень залишилось: {count}",
        "history_shortcuts": (
            "Напиши `detail 1`, щоб відкрити імпорт, або `source 1`, щоб отримати вихідний файл. "
            "Також можна натиснути кнопки нижче."
        ),
        "history_footer": "Використовуй /clarify, щоб повернутися в активну чергу, або відкрий Mini App для повного workbench.",
        "active_statement": "Активна виписка: {name}",
        "resolved_so_far": "Вже розібрано: {count}",
        "remaining_clarifications": "Залишилось уточнень: {count}",
        "no_pending_statement_clarifications": "Зараз немає активних уточнень по виписці.",
        "completed_statement_footer": "Використовуй кнопки нижче, щоб переглянути статус або відкрити Mini App.",
        "latest_statement": "Остання виписка: {name}",
        "source": "Джерело: {value}",
        "imported": "Імпортовано: {value}",
        "status": "Статус: {value}",
        "parsed_items": "Розібрано рядків: {count}",
        "auto_categorized": "Автокатегоризовано: {count}",
        "needs_clarification": "Потрібно уточнити: {count}",
        "history_item_status": "Статус: {value}",
        "history_item_imported": "Імпортовано: {value}",
        "history_item_parsed": "Розібрано: {count}",
        "history_item_auto": "Авто: {count}",
        "history_item_open_clarifications": "Відкритих уточнень: {count}",
        "unsupported_statement_document": "Цей формат документа поки не підтримується для імпорту банківської виписки. Надішли PDF, CSV, XLSX або XLS, або встав рядки виписки сюди.",
        "statement_import_failed": "Не вдалося імпортувати цю виписку просто зараз. Надішли PDF, CSV, XLSX або XLS, або встав рядки виписки сюди. Деталі: {details}",
        "statement_text_not_recognized": "Текст не схожий на банківську виписку.",
        "statement_file_required": "Потрібен файл виписки.",
        "statement_file_type_unsupported": "Формат файла виписки не підтримується. Використовуй PDF, CSV, XLSX або XLS.",
        "statement_file_empty": "Завантажений файл виписки порожній.",
        "statement_clarification_payload_invalid": "Передай або answer_text, або account_type разом із life_sector.",
        "statement_no_pending_for_user": "Для цього Telegram-користувача немає очікуючих уточнень по виписці.",
        "voice_clarification_unavailable": "Локальне голосове уточнення зараз недоступне. Відповідай текстом або встанови локальний speech stack. Деталі: {details}",
        "statement_status_completed": "Завершено",
        "statement_status_clarification_required": "Потрібне уточнення",
        "statement_status_processing": "Обробка",
        "statement_status_failed": "Помилка",
        "account_type_business": "Бізнес",
        "account_type_personal": "Особисте",
        "life_sector_sales_income": "Продажі / Дохід",
        "life_sector_inventory_parts": "Запаси / Запчастини",
        "life_sector_payroll_team": "Команда / Зарплата",
        "life_sector_rent_utilities": "Оренда / Комунальні",
        "life_sector_logistics_transport": "Логістика / Транспорт",
        "life_sector_marketing_growth": "Маркетинг / Зростання",
        "life_sector_taxes_fees": "Податки / Збори",
        "life_sector_tools_software": "Інструменти / Софт",
        "life_sector_owner_draw": "Вивід власника",
        "life_sector_family_living": "Сім'я / Побут",
        "life_sector_savings_debt": "Заощадження / Борги",
        "chat_logged": "Записав: {category} {amount}",
        "chat_need_clarification": "Прийняв. Уточни, це витрата, надходження чи ціль?",
        "photo_recognized": "Чек розпізнано: {category} {amount}",
        "photo_not_recognized": "Не вдалося розпізнати чек. Спробуй ще раз.",
        "receipt_saved": "Чек збережено: {merchant} {amount}. SKU: {sku_count}. Топ позиції: {top_items}.",
        "voice_logged": "Записав з голосу: {category} {amount}",
        "voice_not_recognized": "Не вдалося розпізнати голос. Спробуй ще раз.",
    },
}

STATEMENT_SERVICE_TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        "statement_processing_summary": (
            "Processing bank statement ({parsed_count} items)...\n"
            "Parsed automatically: {auto_count}\n"
            "Need clarification: {unclear_count}"
        ),
        "statement_prompt_intro": "I parsed {auto_count} items automatically. Clarification {ordinal} of {total}:",
        "statement_reason_label": "Reason: {reason}",
        "statement_description_label": "Statement note: {description}",
        "statement_quick_choices_intro": "Quick choices:",
        "statement_prompt_reply_example": (
            "Reply with `1`, another quick-choice number, the label text, or text/voice, for example: `business parts` or `personal family`."
        ),
        "statement_completion_saved": (
            "Statement import complete. All unclear items were resolved and saved into memory."
        ),
        "statement_next_clarification": "Saved. Next clarification {ordinal} of {total}:",
        "statement_prompt_reply_tap": "Reply with a quick-choice number, text/voice, or tap a quick category button.",
        "statement_item_line": "{transaction_type} {amount} KZT to '{counterparty}' on {statement_date}",
        "statement_transaction_income": "Income",
        "statement_transaction_expense": "Expense",
        "statement_suggested_quick_choice": "Suggested quick choice: {choice}",
        "statement_primary_choice_hint": "Fastest confirm now: `1` = {choice}",
        "statement_matched_rules_intro": "Learned precedents:",
        "statement_matched_rule_line": "- {choice}: {explanation}",
        "statement_same_as_before_hint": "Shortcut: reply `same as before` to reuse the learned precedent.",
        "loaded_statement_import_detail": "Loaded statement import detail",
        "statement_import_detail_title": "Statement import detail: {name}",
        "statement_detail_not_found": "That statement import is no longer available.",
        "statement_note": "Import note: {value}",
        "statement_storage": "Storage: {value}",
        "statement_storage_local_file_available": "local file available",
        "statement_storage_local_file_missing": "local file missing",
        "statement_storage_virtual_text": "telegram text retained in database",
        "statement_raw_preview_lines": "Raw preview: showing {shown} of {total} lines",
        "statement_raw_preview_empty": "Raw preview: not retained for this import.",
        "statement_raw_preview_truncated": "Preview is truncated. Open the Mini App for the full retained payload.",
        "send_statement_source": "Send source file",
        "statement_source_caption": "Original statement source: {name}",
        "statement_source_sent": "Sent statement source: {name}",
        "statement_source_not_available": "The original statement source is no longer available.",
        "statement_source_send_failed": "Could not send the statement source right now. Details: {details}",
        "statement_source_short": "Source",
        "back_to_history": "Back to history",
        "statement_detail_footer": "Use the buttons below to resume clarification, send the source file, return to history, or open the Mini App.",
    },
    "ru": {
        "statement_processing_summary": (
            "\u041e\u0431\u0440\u0430\u0431\u043e\u0442\u043a\u0430 \u0431\u0430\u043d\u043a\u043e\u0432\u0441\u043a\u043e\u0439 \u0432\u044b\u043f\u0438\u0441\u043a\u0438 ({parsed_count} \u0441\u0442\u0440\u043e\u043a)...\n"
            "\u0420\u0430\u0437\u043e\u0431\u0440\u0430\u043d\u043e \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438: {auto_count}\n"
            "\u041d\u0443\u0436\u043d\u043e \u0443\u0442\u043e\u0447\u043d\u0438\u0442\u044c: {unclear_count}"
        ),
        "statement_prompt_intro": (
            "\u042f \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u0435\u0441\u043a\u0438 \u0440\u0430\u0437\u043e\u0431\u0440\u0430\u043b {auto_count} \u0441\u0442\u0440\u043e\u043a. "
            "\u0423\u0442\u043e\u0447\u043d\u0435\u043d\u0438\u0435 {ordinal} \u0438\u0437 {total}:"
        ),
        "statement_reason_label": "\u041f\u0440\u0438\u0447\u0438\u043d\u0430: {reason}",
        "statement_description_label": "\u0414\u0435\u0442\u0430\u043b\u0438 \u0438\u0437 \u0432\u044b\u043f\u0438\u0441\u043a\u0438: {description}",
        "statement_quick_choices_intro": "\u0411\u044b\u0441\u0442\u0440\u044b\u0435 \u0432\u0430\u0440\u0438\u0430\u043d\u0442\u044b:",
        "statement_prompt_reply_example": (
            "\u041e\u0442\u0432\u0435\u0442\u044c `1`, \u0434\u0440\u0443\u0433\u0438\u043c \u043d\u043e\u043c\u0435\u0440\u043e\u043c \u0431\u044b\u0441\u0442\u0440\u043e\u0433\u043e \u0432\u044b\u0431\u043e\u0440\u0430, \u0442\u0435\u043a\u0441\u0442\u043e\u043c \u043a\u043d\u043e\u043f\u043a\u0438 \u0438\u043b\u0438 \u0442\u0435\u043a\u0441\u0442\u043e\u043c/\u0433\u043e\u043b\u043e\u0441\u043e\u043c, "
            "\u043d\u0430\u043f\u0440\u0438\u043c\u0435\u0440: `business parts` \u0438\u043b\u0438 `personal family`."
        ),
        "statement_completion_saved": (
            "\u0418\u043c\u043f\u043e\u0440\u0442 \u0432\u044b\u043f\u0438\u0441\u043a\u0438 \u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d. "
            "\u0412\u0441\u0435 \u043d\u0435\u044f\u0441\u043d\u044b\u0435 \u043e\u043f\u0435\u0440\u0430\u0446\u0438\u0438 \u0443\u0442\u043e\u0447\u043d\u0435\u043d\u044b \u0438 \u0441\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u044b \u0432 \u043f\u0430\u043c\u044f\u0442\u044c."
        ),
        "statement_next_clarification": (
            "\u0421\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u043e. \u0421\u043b\u0435\u0434\u0443\u044e\u0449\u0435\u0435 \u0443\u0442\u043e\u0447\u043d\u0435\u043d\u0438\u0435 {ordinal} \u0438\u0437 {total}:"
        ),
        "statement_prompt_reply_tap": (
            "\u041e\u0442\u0432\u0435\u0442\u044c \u043d\u043e\u043c\u0435\u0440\u043e\u043c \u0431\u044b\u0441\u0442\u0440\u043e\u0433\u043e \u0432\u044b\u0431\u043e\u0440\u0430, \u0442\u0435\u043a\u0441\u0442\u043e\u043c/\u0433\u043e\u043b\u043e\u0441\u043e\u043c \u0438\u043b\u0438 "
            "\u043d\u0430\u0436\u043c\u0438 \u043a\u043d\u043e\u043f\u043a\u0443 \u0431\u044b\u0441\u0442\u0440\u043e\u0439 \u043a\u0430\u0442\u0435\u0433\u043e\u0440\u0438\u0438."
        ),
        "statement_item_line": (
            "{transaction_type} {amount} KZT \u0434\u043b\u044f '{counterparty}' \u043e\u0442 {statement_date}"
        ),
        "statement_transaction_income": "\u041f\u043e\u0441\u0442\u0443\u043f\u043b\u0435\u043d\u0438\u0435",
        "statement_transaction_expense": "\u0420\u0430\u0441\u0445\u043e\u0434",
        "statement_suggested_quick_choice": "\u041f\u043e\u0434\u0441\u043a\u0430\u0437\u043a\u0430: {choice}",
        "statement_primary_choice_hint": "\u0411\u044b\u0441\u0442\u0440\u0435\u0435 \u0432\u0441\u0435\u0433\u043e \u0441\u0435\u0439\u0447\u0430\u0441: `1` = {choice}",
        "statement_matched_rules_intro": "\u0423\u0436\u0435 \u0432\u044b\u0443\u0447\u0435\u043d\u043e \u0438\u0437 \u043f\u043e\u0445\u043e\u0436\u0438\u0445 \u043f\u0435\u0440\u0435\u0432\u043e\u0434\u043e\u0432:",
        "statement_matched_rule_line": "- {choice}: {explanation}",
        "statement_same_as_before_hint": (
            "\u0411\u044b\u0441\u0442\u0440\u044b\u0439 \u043e\u0442\u0432\u0435\u0442: \u043d\u0430\u043f\u0438\u0448\u0438 `\u043a\u0430\u043a \u0440\u0430\u043d\u044c\u0448\u0435`, "
            "\u0447\u0442\u043e\u0431\u044b \u043f\u043e\u0432\u0442\u043e\u0440\u0438\u0442\u044c \u0443\u0436\u0435 \u0432\u044b\u0443\u0447\u0435\u043d\u043d\u043e\u0435 \u043f\u0440\u0430\u0432\u0438\u043b\u043e."
        ),
        "send_statement_source": "\u041f\u0440\u0438\u0441\u043b\u0430\u0442\u044c \u0438\u0441\u0445\u043e\u0434\u043d\u0438\u043a",
        "statement_source_caption": "\u0418\u0441\u0445\u043e\u0434\u043d\u0430\u044f \u0432\u044b\u043f\u0438\u0441\u043a\u0430: {name}",
        "statement_source_sent": "\u0418\u0441\u0445\u043e\u0434\u043d\u0438\u043a \u0432\u044b\u043f\u0438\u0441\u043a\u0438 \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d: {name}",
        "statement_source_not_available": "\u0418\u0441\u0445\u043e\u0434\u043d\u0438\u043a \u044d\u0442\u043e\u0439 \u0432\u044b\u043f\u0438\u0441\u043a\u0438 \u0431\u043e\u043b\u044c\u0448\u0435 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u0435\u043d.",
        "statement_source_send_failed": "\u0421\u0435\u0439\u0447\u0430\u0441 \u043d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043e\u0442\u043f\u0440\u0430\u0432\u0438\u0442\u044c \u0438\u0441\u0445\u043e\u0434\u043d\u0438\u043a \u0432\u044b\u043f\u0438\u0441\u043a\u0438. \u0414\u0435\u0442\u0430\u043b\u0438: {details}",
        "statement_source_short": "\u0418\u0441\u0442\u043e\u0447\u043d\u0438\u043a",
        "back_to_history": "\u041d\u0430\u0437\u0430\u0434 \u043a \u0438\u0441\u0442\u043e\u0440\u0438\u0438",
        "statement_detail_footer": "\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0439 \u043a\u043d\u043e\u043f\u043a\u0438 \u043d\u0438\u0436\u0435, \u0447\u0442\u043e\u0431\u044b \u0432\u0435\u0440\u043d\u0443\u0442\u044c\u0441\u044f \u043a \u0443\u0442\u043e\u0447\u043d\u0435\u043d\u0438\u044e, \u043f\u043e\u043b\u0443\u0447\u0438\u0442\u044c \u0438\u0441\u0445\u043e\u0434\u043d\u0438\u043a, \u0432\u0435\u0440\u043d\u0443\u0442\u044c\u0441\u044f \u043a \u0438\u0441\u0442\u043e\u0440\u0438\u0438 \u0438\u043b\u0438 \u043e\u0442\u043a\u0440\u044b\u0442\u044c Mini App.",
    },
    "kk": {
        "statement_processing_summary": (
            "\u0411\u0430\u043d\u043a \u04af\u0437\u0456\u043d\u0434\u0456\u0441\u0456 \u04e9\u04a3\u0434\u0435\u043b\u0443\u0434\u0435 ({parsed_count} \u0436\u043e\u043b)...\n"
            "\u0410\u0432\u0442\u043e\u043c\u0430\u0442\u0442\u044b \u0442\u04af\u0440\u0434\u0435 \u0442\u0430\u043b\u0434\u0430\u043d\u0434\u044b: {auto_count}\n"
            "\u041d\u0430\u049b\u0442\u044b\u043b\u0430\u0443 \u043a\u0435\u0440\u0435\u043a: {unclear_count}"
        ),
        "statement_prompt_intro": (
            "\u041c\u0435\u043d {auto_count} \u0436\u043e\u043b\u0434\u044b \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0442\u044b \u0442\u04af\u0440\u0434\u0435 \u0442\u0430\u043b\u0434\u0430\u0434\u044b\u043c. "
            "{ordinal}/{total} \u043d\u0430\u049b\u0442\u044b\u043b\u0430\u0443:"
        ),
        "statement_reason_label": "\u0421\u0435\u0431\u0435\u0431\u0456: {reason}",
        "statement_description_label": "\u04ae\u0437\u0456\u043d\u0434\u0456 \u0434\u0435\u0440\u0435\u0433\u0456: {description}",
        "statement_quick_choices_intro": "\u0416\u044b\u043b\u0434\u0430\u043c \u043d\u04b1\u0441\u049b\u0430\u043b\u0430\u0440:",
        "statement_prompt_reply_example": (
            "\u041c\u04d9\u0442\u0456\u043d\u043c\u0435\u043d/\u0434\u0430\u0443\u044b\u0441\u043f\u0435\u043d \u0436\u0430\u0443\u0430\u043f \u0431\u0435\u0440, `1`, \u0431\u0430\u0441\u049b\u0430 \u0436\u044b\u043b\u0434\u0430\u043c \u0442\u0430\u04a3\u0434\u0430\u0443 \u043d\u04e9\u043c\u0456\u0440\u0456, \u0431\u0430\u0442\u044b\u0440\u043c\u0430 \u043c\u04d9\u0442\u0456\u043d\u0456 \u043d\u0435\u043c\u0435\u0441\u0435 "
            "\u043c\u044b\u0441\u0430\u043b\u044b: `business parts` \u043d\u0435\u043c\u0435\u0441\u0435 `personal family`."
        ),
        "statement_completion_saved": (
            "\u04ae\u0437\u0456\u043d\u0434\u0456\u043d\u0456 \u0438\u043c\u043f\u043e\u0440\u0442\u0442\u0430\u0443 \u0430\u044f\u049b\u0442\u0430\u043b\u0434\u044b. "
            "\u0411\u0430\u0440\u043b\u044b\u049b \u0442\u04af\u0441\u0456\u043d\u0456\u043a\u0441\u0456\u0437 \u043e\u043f\u0435\u0440\u0430\u0446\u0438\u044f\u043b\u0430\u0440 \u043d\u0430\u049b\u0442\u044b\u043b\u0430\u043d\u044b\u043f, \u0436\u0430\u0434\u049b\u0430 \u0441\u0430\u049b\u0442\u0430\u043b\u0434\u044b."
        ),
        "statement_next_clarification": (
            "\u0421\u0430\u049b\u0442\u0430\u043b\u0434\u044b. \u041a\u0435\u043b\u0435\u0441\u0456 \u043d\u0430\u049b\u0442\u044b\u043b\u0430\u0443 {ordinal}/{total}:"
        ),
        "statement_prompt_reply_tap": (
            "\u0416\u044b\u043b\u0434\u0430\u043c \u0442\u0430\u04a3\u0434\u0430\u0443 \u043d\u04e9\u043c\u0456\u0440\u0456\u043c\u0435\u043d, \u043c\u04d9\u0442\u0456\u043d\u043c\u0435\u043d/\u0434\u0430\u0443\u044b\u0441\u043f\u0435\u043d \u0436\u0430\u0443\u0430\u043f \u0431\u0435\u0440 "
            "\u043d\u0435\u043c\u0435\u0441\u0435 \u0436\u044b\u043b\u0434\u0430\u043c \u0441\u0430\u043d\u0430\u0442 \u0431\u0430\u0442\u044b\u0440\u043c\u0430\u0441\u044b\u043d \u0431\u0430\u0441."
        ),
        "statement_item_line": (
            "{transaction_type} {amount} KZT '{counterparty}' \u04af\u0448\u0456\u043d {statement_date} \u043a\u04af\u043d\u0456"
        ),
        "statement_transaction_income": "\u041a\u0456\u0440\u0456\u0441",
        "statement_transaction_expense": "\u0428\u044b\u0493\u044b\u0441",
        "statement_suggested_quick_choice": (
            "\u04b0\u0441\u044b\u043d\u044b\u043b\u0493\u0430\u043d \u0436\u044b\u043b\u0434\u0430\u043c \u0442\u0430\u04a3\u0434\u0430\u0443: {choice}"
        ),
        "statement_primary_choice_hint": "\u049a\u0430\u0437\u0456\u0440 \u0435\u04a3 \u0436\u044b\u043b\u0434\u0430\u043c\u044b: `1` = {choice}",
        "statement_matched_rules_intro": "\u04b0\u049b\u0441\u0430\u0441 \u0430\u0443\u0434\u0430\u0440\u044b\u043c\u0434\u0430\u0440\u0434\u0430\u043d \u04af\u0439\u0440\u0435\u043d\u0433\u0435\u043d \u0435\u0440\u0435\u0436\u0435\u043b\u0435\u0440:",
        "statement_matched_rule_line": "- {choice}: {explanation}",
        "statement_same_as_before_hint": (
            "\u049a\u044b\u0441\u049b\u0430 \u0436\u0430\u0443\u0430\u043f: \u04af\u0439\u0440\u0435\u043d\u0433\u0435\u043d \u0435\u0440\u0435\u0436\u0435\u043d\u0456 \u049b\u0430\u0439\u0442\u0430 "
            "\u049b\u043e\u043b\u0434\u0430\u043d\u0443 \u04af\u0448\u0456\u043d `\u0431\u04b1\u0440\u044b\u043d\u0493\u044b\u0434\u0430\u0439` \u0434\u0435\u043f \u0436\u0430\u0437."
        ),
        "send_statement_source": "\u0414\u0435\u0440\u0435\u043a\u043a\u04e9\u0437 \u0444\u0430\u0439\u043b\u044b\u043d \u0436\u0456\u0431\u0435\u0440\u0443",
        "statement_source_caption": "\u04ae\u0437\u0456\u043d\u0434\u0456\u043d\u0456\u04a3 \u0431\u0430\u0441\u0442\u0430\u043f\u049b\u044b \u0434\u0435\u0440\u0435\u043a\u043a\u04e9\u0437\u0456: {name}",
        "statement_source_sent": "\u04ae\u0437\u0456\u043d\u0434\u0456 \u0434\u0435\u0440\u0435\u043a\u043a\u04e9\u0437\u0456 \u0436\u0456\u0431\u0435\u0440\u0456\u043b\u0434\u0456: {name}",
        "statement_source_not_available": "\u0411\u04b1\u043b \u04af\u0437\u0456\u043d\u0434\u0456\u043d\u0456\u04a3 \u0431\u0430\u0441\u0442\u0430\u043f\u049b\u044b \u0434\u0435\u0440\u0435\u043a\u043a\u04e9\u0437\u0456 \u0435\u043d\u0434\u0456 \u049b\u043e\u043b\u0436\u0435\u0442\u0456\u043c\u0441\u0456\u0437.",
        "statement_source_send_failed": "\u04ae\u0437\u0456\u043d\u0434\u0456 \u0434\u0435\u0440\u0435\u043a\u043a\u04e9\u0437\u0456\u043d \u049b\u0430\u0437\u0456\u0440 \u0436\u0456\u0431\u0435\u0440\u0443 \u043c\u04af\u043c\u043a\u0456\u043d \u0431\u043e\u043b\u043c\u0430\u0434\u044b. \u041c\u04d9\u043d-\u0436\u0430\u0439: {details}",
        "statement_source_short": "\u0414\u0435\u0440\u0435\u043a\u043a\u04e9\u0437",
        "back_to_history": "\u0422\u0430\u0440\u0438\u0445\u049b\u0430 \u049b\u0430\u0439\u0442\u0443",
        "statement_detail_footer": "\u0422\u04e9\u043c\u0435\u043d\u0434\u0435\u0433\u0456 \u0431\u0430\u0442\u044b\u0440\u043c\u0430\u043b\u0430\u0440 \u0430\u0440\u049b\u044b\u043b\u044b \u043d\u0430\u049b\u0442\u044b\u043b\u0430\u0443\u0493\u0430 \u049b\u0430\u0439\u0442\u044b\u043f, \u0434\u0435\u0440\u0435\u043a\u043a\u04e9\u0437 \u0444\u0430\u0439\u043b\u044b\u043d \u0430\u043b\u044b\u043f, \u0442\u0430\u0440\u0438\u0445\u049b\u0430 \u043e\u0440\u0430\u043b\u0443 \u043d\u0435\u043c\u0435\u0441\u0435 Mini App-\u0442\u044b \u0430\u0448\u0443\u0493\u0430 \u0431\u043e\u043b\u0430\u0434\u044b.",
    },
    "uk": {
        "statement_processing_summary": (
            "\u041e\u0431\u0440\u043e\u0431\u043a\u0430 \u0431\u0430\u043d\u043a\u0456\u0432\u0441\u044c\u043a\u043e\u0457 \u0432\u0438\u043f\u0438\u0441\u043a\u0438 ({parsed_count} \u0440\u044f\u0434\u043a\u0456\u0432)...\n"
            "\u0410\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u043d\u043e \u0440\u043e\u0437\u0456\u0431\u0440\u0430\u043d\u043e: {auto_count}\n"
            "\u041f\u043e\u0442\u0440\u0456\u0431\u043d\u043e \u0443\u0442\u043e\u0447\u043d\u0438\u0442\u0438: {unclear_count}"
        ),
        "statement_prompt_intro": (
            "\u042f \u0430\u0432\u0442\u043e\u043c\u0430\u0442\u0438\u0447\u043d\u043e \u0440\u043e\u0437\u0456\u0431\u0440\u0430\u0432 {auto_count} \u0440\u044f\u0434\u043a\u0456\u0432. "
            "\u0423\u0442\u043e\u0447\u043d\u0435\u043d\u043d\u044f {ordinal} \u0437 {total}:"
        ),
        "statement_reason_label": "\u041f\u0440\u0438\u0447\u0438\u043d\u0430: {reason}",
        "statement_description_label": "\u0414\u0435\u0442\u0430\u043b\u0456 \u0437 \u0432\u0438\u043f\u0438\u0441\u043a\u0438: {description}",
        "statement_quick_choices_intro": "\u0428\u0432\u0438\u0434\u043a\u0456 \u0432\u0430\u0440\u0456\u0430\u043d\u0442\u0438:",
        "statement_prompt_reply_example": (
            "\u0412\u0456\u0434\u043f\u043e\u0432\u0456\u0434\u0430\u0439 `1`, \u0456\u043d\u0448\u0438\u043c \u043d\u043e\u043c\u0435\u0440\u043e\u043c \u0448\u0432\u0438\u0434\u043a\u043e\u0433\u043e \u0432\u0438\u0431\u043e\u0440\u0443, \u0442\u0435\u043a\u0441\u0442\u043e\u043c \u043a\u043d\u043e\u043f\u043a\u0438 \u0430\u0431\u043e \u0442\u0435\u043a\u0441\u0442\u043e\u043c/\u0433\u043e\u043b\u043e\u0441\u043e\u043c, "
            "\u043d\u0430\u043f\u0440\u0438\u043a\u043b\u0430\u0434: `business parts` \u0430\u0431\u043e `personal family`."
        ),
        "statement_completion_saved": (
            "\u0406\u043c\u043f\u043e\u0440\u0442 \u0432\u0438\u043f\u0438\u0441\u043a\u0438 \u0437\u0430\u0432\u0435\u0440\u0448\u0435\u043d\u043e. "
            "\u0423\u0441\u0456 \u043d\u0435\u044f\u0441\u043d\u0456 \u043e\u043f\u0435\u0440\u0430\u0446\u0456\u0457 \u0443\u0442\u043e\u0447\u043d\u0435\u043d\u043e \u0442\u0430 \u0437\u0431\u0435\u0440\u0435\u0436\u0435\u043d\u043e \u0432 \u043f\u0430\u043c'\u044f\u0442\u044c."
        ),
        "statement_next_clarification": (
            "\u0417\u0431\u0435\u0440\u0435\u0436\u0435\u043d\u043e. \u041d\u0430\u0441\u0442\u0443\u043f\u043d\u0435 \u0443\u0442\u043e\u0447\u043d\u0435\u043d\u043d\u044f {ordinal} \u0437 {total}:"
        ),
        "statement_prompt_reply_tap": (
            "\u0412\u0456\u0434\u043f\u043e\u0432\u0456\u0434\u0430\u0439 \u043d\u043e\u043c\u0435\u0440\u043e\u043c \u0448\u0432\u0438\u0434\u043a\u043e\u0433\u043e \u0432\u0438\u0431\u043e\u0440\u0443, \u0442\u0435\u043a\u0441\u0442\u043e\u043c/\u0433\u043e\u043b\u043e\u0441\u043e\u043c "
            "\u0430\u0431\u043e \u043d\u0430\u0442\u0438\u0441\u043d\u0438 \u043a\u043d\u043e\u043f\u043a\u0443 \u0448\u0432\u0438\u0434\u043a\u043e\u0457 \u043a\u0430\u0442\u0435\u0433\u043e\u0440\u0456\u0457."
        ),
        "statement_item_line": (
            "{transaction_type} {amount} KZT \u0434\u043b\u044f '{counterparty}' \u0432\u0456\u0434 {statement_date}"
        ),
        "statement_transaction_income": "\u041d\u0430\u0434\u0445\u043e\u0434\u0436\u0435\u043d\u043d\u044f",
        "statement_transaction_expense": "\u0412\u0438\u0442\u0440\u0430\u0442\u0430",
        "statement_suggested_quick_choice": (
            "\u041f\u0456\u0434\u043a\u0430\u0437\u043a\u0430 \u0434\u043b\u044f \u0448\u0432\u0438\u0434\u043a\u043e\u0433\u043e \u0432\u0438\u0431\u043e\u0440\u0443: {choice}"
        ),
        "statement_primary_choice_hint": "\u041d\u0430\u0439\u0448\u0432\u0438\u0434\u0448\u0435 \u0437\u0430\u0440\u0430\u0437: `1` = {choice}",
        "statement_matched_rules_intro": "\u0423\u0436\u0435 \u0432\u0438\u0432\u0447\u0435\u043d\u043e \u0437 \u0441\u0445\u043e\u0436\u0438\u0445 \u043f\u0435\u0440\u0435\u043a\u0430\u0437\u0456\u0432:",
        "statement_matched_rule_line": "- {choice}: {explanation}",
        "statement_same_as_before_hint": (
            "\u0428\u0432\u0438\u0434\u043a\u0430 \u0432\u0456\u0434\u043f\u043e\u0432\u0456\u0434\u044c: \u043d\u0430\u043f\u0438\u0448\u0456\u0442\u044c `\u044f\u043a \u0440\u0430\u043d\u0456\u0448\u0435`, "
            "\u0449\u043e\u0431 \u043f\u043e\u0432\u0442\u043e\u0440\u0438\u0442\u0438 \u0432\u0436\u0435 \u0432\u0438\u0432\u0447\u0435\u043d\u0435 \u043f\u0440\u0430\u0432\u0438\u043b\u043e."
        ),
        "send_statement_source": "\u041d\u0430\u0434\u0456\u0441\u043b\u0430\u0442\u0438 \u0434\u0436\u0435\u0440\u0435\u043b\u043e",
        "statement_source_caption": "\u041e\u0440\u0438\u0433\u0456\u043d\u0430\u043b \u0432\u0438\u043f\u0438\u0441\u043a\u0438: {name}",
        "statement_source_sent": "\u0414\u0436\u0435\u0440\u0435\u043b\u043e \u0432\u0438\u043f\u0438\u0441\u043a\u0438 \u043d\u0430\u0434\u0456\u0441\u043b\u0430\u043d\u043e: {name}",
        "statement_source_not_available": "\u041e\u0440\u0438\u0433\u0456\u043d\u0430\u043b \u0446\u0456\u0454\u0457 \u0432\u0438\u043f\u0438\u0441\u043a\u0438 \u0431\u0456\u043b\u044c\u0448\u0435 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u043d\u0438\u0439.",
        "statement_source_send_failed": "\u0417\u0430\u0440\u0430\u0437 \u043d\u0435 \u0432\u0434\u0430\u043b\u043e\u0441\u044f \u043d\u0430\u0434\u0456\u0441\u043b\u0430\u0442\u0438 \u0434\u0436\u0435\u0440\u0435\u043b\u043e \u0432\u0438\u043f\u0438\u0441\u043a\u0438. \u0414\u0435\u0442\u0430\u043b\u0456: {details}",
        "statement_source_short": "\u0414\u0436\u0435\u0440\u0435\u043b\u043e",
        "back_to_history": "\u041d\u0430\u0437\u0430\u0434 \u0434\u043e \u0456\u0441\u0442\u043e\u0440\u0456\u0457",
        "statement_detail_footer": "\u0412\u0438\u043a\u043e\u0440\u0438\u0441\u0442\u0430\u0439 \u043a\u043d\u043e\u043f\u043a\u0438 \u043d\u0438\u0436\u0447\u0435, \u0449\u043e\u0431 \u043f\u043e\u043d\u043e\u0432\u0438\u0442\u0438 \u0443\u0442\u043e\u0447\u043d\u0435\u043d\u043d\u044f, \u043d\u0430\u0434\u0456\u0441\u043b\u0430\u0442\u0438 \u0434\u0436\u0435\u0440\u0435\u043b\u043e, \u043f\u043e\u0432\u0435\u0440\u043d\u0443\u0442\u0438\u0441\u044f \u0434\u043e \u0456\u0441\u0442\u043e\u0440\u0456\u0457 \u0430\u0431\u043e \u0432\u0456\u0434\u043a\u0440\u0438\u0442\u0438 Mini App.",
    },
}


def normalize_language(language_code: str | None, *, default: str = "ru") -> str:
    if not language_code:
        return default
    normalized = language_code.strip().lower().replace("_", "-").split("-", maxsplit=1)[0]
    normalized = LANGUAGE_ALIASES.get(normalized, normalized)
    return normalized if normalized in SUPPORTED_LANGUAGES else default


async def resolve_user_language(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    fallback_language_code: str | None = None,
    default: str = "ru",
) -> str:
    result = await session.execute(
        select(UserProfile.preferred_language).where(UserProfile.telegram_user_id == telegram_user_id)
    )
    preferred_language = result.scalar_one_or_none()
    return normalize_language(preferred_language or fallback_language_code, default=default)


def text(key: str, lang: str = "en", **kwargs) -> str:
    language = normalize_language(lang)
    template = (
        TRANSLATIONS.get(language, TRANSLATIONS["en"]).get(key)
        or STATEMENT_SERVICE_TRANSLATIONS.get(language, STATEMENT_SERVICE_TRANSLATIONS["en"]).get(key)
        or TRANSLATIONS["en"].get(key)
        or STATEMENT_SERVICE_TRANSLATIONS["en"][key]
    )
    return template.format(**kwargs)


def statement_status_label(status: str, lang: str = "en") -> str:
    return text(f"statement_status_{status}", lang) if f"statement_status_{status}" in TRANSLATIONS["en"] else status.replace("_", " ").title()


def account_type_label(account_type: str, lang: str = "en") -> str:
    return text(f"account_type_{account_type}", lang) if f"account_type_{account_type}" in TRANSLATIONS["en"] else account_type.title()


def life_sector_label(life_sector: str, lang: str = "en") -> str:
    return (
        text(f"life_sector_{life_sector}", lang)
        if f"life_sector_{life_sector}" in TRANSLATIONS["en"]
        else life_sector.replace("_", " ").title()
    )


def clarification_choice_label(account_type: str, life_sector: str, lang: str = "en") -> str:
    return f"{account_type_label(account_type, lang)} / {life_sector_label(life_sector, lang)}"
